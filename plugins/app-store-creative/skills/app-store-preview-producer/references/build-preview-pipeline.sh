#!/usr/bin/env bash
#
# build-preview-pipeline.sh
# Reference Assembly Pipeline for Apple App Store Preview Videos
#
# Demonstrates RFC #46 4-Layer workflow:
# 1. Inputs:    .creative/inputs/video/ (final master source video)
# 2. Pipeline:  .creative/pipeline/ (scripts and contracts)
# 3. Cache:     .creative/.cache/ (scenes, audio cuts, work directory)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
PIPELINE_DIR="$REPO_ROOT/.creative/pipeline"
INPUTS_DIR="$REPO_ROOT/.creative/inputs"
CACHE_DIR="$REPO_ROOT/.creative/.cache"

SCENES_DIR="$CACHE_DIR/scenes"
WORK_DIR="$CACHE_DIR/video_work"
mkdir -p "$WORK_DIR" "$INPUTS_DIR/video"

PLUGIN_SCRIPTS="$REPO_ROOT/plugins/app-store-creative/skills/app-store-creative/runtime/scripts"

# 1. Synthesize 24.0s Studio Ambient BGM (48kHz stereo, vocal notch filter)
echo "==> Synthesizing 24s ambient electronic BGM..."
python3 "$PLUGIN_SCRIPTS/synthesize_ambient_bgm.py" \
  --duration 24.0 \
  --output "$WORK_DIR/bgm.wav"

# 2. (Optional) Synthesize or load speech voiceover narration (e.g. via edge-tts or AVSpeechSynthesizer)
# In this template, if voiceover.wav exists, apply sidechain ducking (-12 dB) and -16.0 LUFS normalization
if [ -f "$WORK_DIR/voiceover.wav" ]; then
  echo "==> Mixing voiceover and BGM with sidechain ducking (-12 dB, -16 LUFS)..."
  python3 "$PLUGIN_SCRIPTS/audio_ducking_mixer.py" \
    --bgm "$WORK_DIR/bgm.wav" \
    --voice "$WORK_DIR/voiceover.wav" \
    --ducking-db -12.0 \
    --target-lufs -16.0 \
    --output "$WORK_DIR/master_audio.wav"
else
  echo "==> No voiceover provided; using pure ambient BGM as audio master..."
  cp "$WORK_DIR/bgm.wav" "$WORK_DIR/master_audio.wav"
fi

# 3. Render video track across scenes with smooth transitions (example: 4 scenes x 6s = 24s)
echo "==> Stitching video scenes with FFmpeg..."
if [ -f "$SCENES_DIR/scene_01.png" ]; then
  ffmpeg -y -v error -loop 1 -framerate 30 -t 6.0 -i "$SCENES_DIR/scene_01.png" \
    -vf "format=yuv420p,fade=t=in:st=0:d=0.3" -c:v libx264 -preset fast -crf 17 -r 30 "$WORK_DIR/v1.mp4"

  # Concatenate video segments
  cat > "$WORK_DIR/vconcat.txt" <<EOF
file '$WORK_DIR/v1.mp4'
EOF
  ffmpeg -y -v error -f concat -safe 0 -i "$WORK_DIR/vconcat.txt" -c copy "$WORK_DIR/video_only.mp4"

  # 4. Mux final video and master audio into App Store compliant MP4
  echo "==> Muxing final App Preview into .creative/inputs/video/..."
  ffmpeg -y -v error -i "$WORK_DIR/video_only.mp4" -i "$WORK_DIR/master_audio.wav" \
    -c:v libx264 -profile:v high -level 4.0 -pix_fmt yuv420p -r 30 -crf 18 \
    -c:a aac -b:a 192k -ar 48000 -ac 2 \
    -movflags +faststart -t 24.0 \
    "$INPUTS_DIR/video/preview_source.mp4"

  echo "==> Successfully assembled: $INPUTS_DIR/video/preview_source.mp4"
fi
