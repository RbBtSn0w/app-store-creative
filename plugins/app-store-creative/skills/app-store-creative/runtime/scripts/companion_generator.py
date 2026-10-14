"""Zero-server standalone companion artifact generator for App Store Creative (v2.0)."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

import studio_contract


ROLE_SEQUENCE = [
    "Hero",
    "Core Action",
    "Depth",
    "Ecosystem",
    "Trust / Privacy",
]


def svg_placeholder(card_id: str, headline: str, width: int = 1440, height: int = 900) -> str:
    """Generate a lightweight SVG data URL placeholder when screenshot is absent."""
    safe_title = html.escape(headline or card_id)
    safe_id = html.escape(card_id)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1E2235"/>
      <stop offset="100%" stop-color="#0E111A"/>
    </linearGradient>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
      <feDropShadow dx="0" dy="8" stdDeviation="16" flood-color="#000000" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="{width}" height="{height}" rx="18" fill="url(#bg)" filter="url(#shadow)" stroke="#FFFFFF" stroke-opacity="0.12" stroke-width="2"/>
  <rect width="{width}" height="44" rx="18" fill="#181B28"/>
  <rect y="26" width="{width}" height="18" fill="#181B28"/>
  <circle cx="28" cy="22" r="6" fill="#FF5F56"/>
  <circle cx="48" cy="22" r="6" fill="#FFBD2E"/>
  <circle cx="68" cy="22" r="6" fill="#27C93F"/>
  <text x="{width / 2}" y="{height / 2 - 20}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif" font-size="34" font-weight="700" fill="#FFFFFF" opacity="0.9">{safe_title}</text>
  <text x="{width / 2}" y="{height / 2 + 30}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', monospace" font-size="20" font-weight="500" fill="#818CF8" opacity="0.8">Card ID: {safe_id}</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def generate_companion(
    repo_root: Path,
    config_path: Path | None = None,
    output_path: Path | None = None,
    target: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Generate a zero-server self-contained companion HTML artifact from creative.config.json."""
    repo = Path(repo_root).resolve()
    cfg_file = (config_path if config_path and Path(config_path).is_absolute() else repo / (config_path or "creative.config.json")).resolve()
    if not cfg_file.is_file():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    with open(cfg_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    studio_contract.check_config(config)

    targets = config.get("targets", ["mac_16_10"])
    chosen_target = target or targets[0]
    default_locale = config.get("project", {}).get("defaultLocale", "en-US")
    chosen_locale = locale or default_locale

    project_name = config.get("project", {}).get("name", "App Store Creative")
    app_id = config.get("project", {}).get("id", "app")

    cards_data = []
    raw_cards = config.get("cards", [])
    for idx, raw_card in enumerate(raw_cards):
        resolved, localized = studio_contract.resolve_card(config, raw_card, chosen_target, chosen_locale)
        card_id = raw_card["id"]
        role = raw_card.get("role") or (ROLE_SEQUENCE[idx] if idx < len(ROLE_SEQUENCE) else f"Slide {idx + 1}")
        headline = resolved.get("headline", "")
        subheadline = resolved.get("subheadline", "")
        layout = resolved.get("layout", "mac_native_hero")
        offset = resolved.get("deviceOffset", {})

        rotate_x = float(offset.get("rotateX", 0))
        rotate_y = float(offset.get("rotateY", 0))
        rotate = float(offset.get("rotate", 0))
        scale = float(offset.get("scale", 1.0))
        x = float(offset.get("x", 0))
        y = float(offset.get("y", 0))

        screenshot_name = resolved.get("screenshot")
        img_url = ""
        if screenshot_name:
            try:
                asset_path = studio_contract.local_asset(repo, screenshot_name, config)
                data = asset_path.read_bytes()
                mime = "image/jpeg" if data.startswith(b"\xff\xd8") else "image/png"
                img_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            except Exception:
                img_url = svg_placeholder(card_id, headline)
        else:
            img_url = svg_placeholder(card_id, headline)

        cards_data.append({
            "id": card_id,
            "role": role,
            "headline": headline,
            "subheadline": subheadline,
            "layout": layout,
            "rotateX": rotate_x,
            "rotateY": rotate_y,
            "rotate": rotate,
            "scale": scale,
            "x": x,
            "y": y,
            "img": img_url,
        })

    is_mac = chosen_target.startswith("mac_")
    aspect_ratio_class = "aspect-[16/10]" if is_mac else "aspect-[9/19.5]"
    stage_max_height = "max-h-[260px]" if is_mac else "max-h-[380px]"

    out_file = (output_path if output_path and Path(output_path).is_absolute() else repo / (output_path or ".creative/companion.html")).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    cards_json = json.dumps(cards_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(project_name)} - 伴随式调优面板 (Companion)</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    .glass-surface {{
      background: rgba(255, 255, 255, 0.65);
      backdrop-filter: blur(28px) saturate(190%);
      -webkit-backdrop-filter: blur(28px) saturate(190%);
      border: 1px solid rgba(255, 255, 255, 0.45);
      box-shadow: 0 30px 60px -15px rgba(15, 23, 42, 0.25), 0 0 0 1px rgba(255, 255, 255, 0.4) inset;
    }}
    .dark-glass-surface {{
      background: rgba(15, 18, 28, 0.85);
      backdrop-filter: blur(32px) saturate(180%);
      -webkit-backdrop-filter: blur(32px) saturate(180%);
      border: 1px solid rgba(255, 255, 255, 0.15);
      box-shadow: 0 35px 70px -15px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
    }}
    .native-window-shadow {{
      box-shadow: 0 45px 90px -20px rgba(0, 0, 0, 0.65), 0 20px 40px -15px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.15);
    }}
    .floating-badge {{
      animation: gentle-float 4.5s ease-in-out infinite alternate;
    }}
    @keyframes gentle-float {{
      0% {{ transform: translateY(0px) rotate(0deg); }}
      100% {{ transform: translateY(-6px) rotate(-1deg); }}
    }}
  </style>
</head>
<body class="bg-[#0A0D14] text-slate-100 antialiased p-4">
  <div class="max-w-6xl mx-auto space-y-4">

    <!-- Top Header & Zero-Server Badge -->
    <header class="bg-[#121624] border border-white/10 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-md">
      <div>
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            ZERO-SERVER COMPANION
          </span>
          <span class="text-xs text-white/50">{html.escape(project_name)} · {html.escape(chosen_target)} · {html.escape(chosen_locale)}</span>
        </div>
        <h1 class="text-lg font-bold text-white mt-1">伴随式视觉调优面板 (3D 透视 + 实时审阅指令)</h1>
      </div>
      <div class="flex items-center gap-2">
        <button id="btn-export-directives" onclick="downloadDirectivesJson()" class="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition flex items-center gap-1.5">
          <span>💾 导出 review-directives.json</span>
        </button>
        <button id="btn-sync-agent" onclick="syncDirectivesToAgent()" class="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition flex items-center gap-1.5">
          <span>⚡ 同步审阅指令给 Agent</span>
        </button>
      </div>
    </header>

    <!-- Card Selector -->
    <div class="flex flex-wrap items-center gap-2 border-b border-white/10 pb-3" id="cards-nav">
      <!-- Generated dynamically -->
    </div>

    <!-- Main Workspace (Canvas + Inspector) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">

      <!-- LEFT: Canvas Stage (7 cols) -->
      <div class="lg:col-span-7">
        <div id="canvas-card" class="relative w-full {aspect_ratio_class} rounded-2xl overflow-hidden shadow-2xl border border-white/20 select-none flex flex-col justify-between p-6 transition-all duration-500"
             style="background: radial-gradient(circle at 75% 20%, rgba(99, 102, 241, 0.25), transparent 45%), radial-gradient(circle at 20% 80%, rgba(217, 70, 239, 0.25), transparent 50%), linear-gradient(145deg, #0A0E1A 0%, #1E1B4B 50%, #311042 100%);">
          
          <!-- Liquid Glass Ambient Blurs -->
          <div class="absolute -top-16 -right-16 w-80 h-80 rounded-full bg-indigo-500/15 blur-3xl pointer-events-none"></div>
          <div class="absolute -bottom-20 -left-20 w-96 h-96 rounded-full bg-fuchsia-500/15 blur-3xl pointer-events-none"></div>

          <!-- Hotkey / Status pill -->
          <div id="floating-badge" class="floating-badge absolute top-5 right-5 z-20 px-3 py-1.5 rounded-xl dark-glass-surface flex items-center gap-1.5 text-xs font-bold text-white shadow-xl">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span class="text-[11px] text-white/80 font-medium font-mono" id="disp-layout">{html.escape(cards_data[0]['layout'] if cards_data else 'mac_native_hero')}</span>
          </div>

          <!-- Headline & Subheadline -->
          <div id="copy-container" class="relative z-10 space-y-1">
            <div class="flex items-center gap-2">
              <span class="text-[10px] font-bold tracking-widest text-indigo-300 uppercase font-mono" id="disp-tag">CARD 01 · HERO</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> 真实运行态截屏
              </span>
            </div>
            <h2 id="disp-headline" class="text-xl sm:text-2xl font-extrabold text-white tracking-tight leading-tight">
              {html.escape(cards_data[0]['headline'] if cards_data else '')}
            </h2>
            <p id="disp-subheadline" class="text-xs text-white/75 max-w-lg">
              {html.escape(cards_data[0]['subheadline'] if cards_data else '')}
            </p>
          </div>

          <!-- 3D Perspective Stage -->
          <div id="stage-container" class="relative z-10 flex-1 min-h-0 flex items-center justify-center my-1" style="perspective: 1200px;">
            <div id="stage-window" class="w-auto max-w-full {stage_max_height} flex items-center justify-center transition-transform duration-150 ease-out"
                 style="transform: translate3d({cards_data[0]['x']}px, {cards_data[0]['y']}px, 0) scale({cards_data[0]['scale']}) rotate({cards_data[0]['rotate']}deg) rotateX({cards_data[0]['rotateX']}deg) rotateY({cards_data[0]['rotateY']}deg); transform-style: preserve-3d;">
              <div class="rounded-xl overflow-hidden native-window-shadow border border-white/20 {stage_max_height} flex">
                <img id="disp-img" class="object-contain {stage_max_height} w-auto select-none pointer-events-none" src="" alt="Capture">
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Interactive Controls & Agent Mailbox (5 cols) -->
      <div class="lg:col-span-5 space-y-4">

        <!-- 3D Spatial Sliders -->
        <div class="bg-[#121624] border border-white/10 rounded-2xl p-4 space-y-3">
          <div class="flex items-center justify-between border-b border-white/10 pb-2">
            <h3 class="text-xs font-semibold text-white uppercase tracking-wider font-mono">3D Spatial & Pose</h3>
            <div class="flex items-center gap-1.5">
              <button id="btn-pose-hero" onclick="applyPose('hero')" class="px-2 py-0.5 text-[10px] rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 font-medium transition">Hero 3D</button>
              <button id="btn-pose-inward" onclick="applyPose('inward')" class="px-2 py-0.5 text-[10px] rounded bg-white/5 text-white/70 hover:bg-white/10 border border-transparent font-medium transition">Inward</button>
              <button id="btn-pose-flat" onclick="applyPose('flat')" class="px-2 py-0.5 text-[10px] rounded bg-white/5 text-white/70 hover:bg-white/10 border border-transparent font-medium transition">Flat</button>
              <button onclick="resetCardPose()" class="px-1.5 py-0.5 text-[10px] rounded text-white/40 hover:text-white transition" title="重置为当前卡片初始姿态">重置</button>
            </div>
          </div>

          <div class="space-y-2.5 text-xs">
            <div>
              <div class="flex justify-between text-white/70 mb-1">
                <span>Pitch / 俯仰 (rotateX)</span>
                <span id="val-pitch" class="font-mono text-indigo-300">0°</span>
              </div>
              <input id="slider-pitch" type="range" min="-15" max="25" step="1" value="0" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
            </div>

            <div>
              <div class="flex justify-between text-white/70 mb-1">
                <span>Yaw / 偏航 (rotateY)</span>
                <span id="val-yaw" class="font-mono text-indigo-300">0°</span>
              </div>
              <input id="slider-yaw" type="range" min="-20" max="20" step="1" value="0" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
            </div>

            <div>
              <div class="flex justify-between text-white/70 mb-1">
                <span>Roll / 平面旋转 (rotate)</span>
                <span id="val-roll" class="font-mono text-indigo-300">0°</span>
              </div>
              <input id="slider-roll" type="range" min="-15" max="15" step="0.5" value="0" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
            </div>

            <div>
              <div class="flex justify-between text-white/70 mb-1">
                <span>Scale / 缩放</span>
                <span id="val-scale" class="font-mono text-indigo-300">1.00x</span>
              </div>
              <input id="slider-scale" type="range" min="0.75" max="1.30" step="0.01" value="1.00" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
            </div>

            <div class="grid grid-cols-2 gap-2">
              <div>
                <div class="flex justify-between text-white/70 mb-1">
                  <span>Offset X</span>
                  <span id="val-x" class="font-mono text-indigo-300">0px</span>
                </div>
                <input id="slider-x" type="range" min="-80" max="80" step="1" value="0" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
              </div>
              <div>
                <div class="flex justify-between text-white/70 mb-1">
                  <span>Offset Y</span>
                  <span id="val-y" class="font-mono text-indigo-300">0px</span>
                </div>
                <input id="slider-y" type="range" min="-80" max="80" step="1" value="0" oninput="update3D()" class="w-full cursor-pointer accent-indigo-500" />
              </div>
            </div>
          </div>
        </div>

        <!-- Copy & Agent Review Directives -->
        <div class="bg-[#121624] border border-white/10 rounded-2xl p-4 space-y-3">
          <div class="flex items-center justify-between border-b border-white/10 pb-2">
            <h3 class="text-xs font-semibold text-white uppercase tracking-wider font-mono">Agent 协同指令 (Review Directives)</h3>
            <span class="text-[10px] text-emerald-400 font-mono">Zero-Server Ready</span>
          </div>

          <div class="space-y-2 text-xs">
            <div>
              <label class="block text-white/70 mb-1">卡片主标题 (Headline)</label>
              <input id="input-headline" type="text" oninput="updateCopy()" class="w-full bg-[#1A1F2C] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label class="block text-white/70 mb-1">卡片副标题 (Subheadline)</label>
              <input id="input-subheadline" type="text" oninput="updateCopy()" class="w-full bg-[#1A1F2C] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500" />
            </div>
            <div>
              <label class="block text-white/70 mb-1">人类审查指令 (Directives for Agent)</label>
              <textarea id="input-directive" rows="2" oninput="updateDirective()" placeholder="例如：将窗口向左微调 3°，强化剪贴板极速粘贴概念..." class="w-full bg-[#1A1F2C] border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"></textarea>
            </div>

            <div class="flex gap-2 pt-1">
              <button onclick="syncDirectivesToAgent()" class="flex-1 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition text-xs flex items-center justify-center gap-1">
                <span>⚡ 同步给 Agent</span>
              </button>
              <button onclick="downloadDirectivesJson()" class="px-3 py-1.5 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/40 border border-emerald-500/40 text-emerald-200 text-xs">
                <span>💾 下载 JSON</span>
              </button>
              <button onclick="copyDirectiveMarkdown()" class="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-white text-xs">
                <span>📋 复制指令</span>
              </button>
            </div>
            <p id="sync-status" class="text-[11px] text-emerald-300 font-medium hidden"></p>
          </div>
        </div>

      </div>
    </div>
  </div>

  <script>
    const target = "{chosen_target}";
    const locale = "{chosen_locale}";
    const cards = {cards_json};
    let currentIdx = 0;
    const critiqueDirectivesByCard = {{}};

    const initialCardPoses = cards.map(c => ({{
      rotateX: c.rotateX,
      rotateY: c.rotateY,
      rotate: c.rotate,
      scale: c.scale,
      x: c.x,
      y: c.y
    }}));

    function renderNav() {{
      const nav = document.getElementById('cards-nav');
      nav.innerHTML = cards.map((c, idx) => `
        <button onclick="selectCard(${{idx}})" id="card-btn-${{idx}}" class="px-3 py-1.5 rounded-xl border text-xs font-medium transition flex items-center gap-2 ${{idx === currentIdx ? 'bg-indigo-600/20 border-indigo-500 text-white shadow-sm' : 'bg-white/5 border-white/10 text-white/60 hover:text-white'}}">
          <span class="font-mono text-[10px] text-indigo-300">CARD 0${{idx+1}}</span>
          <span class="text-[10px] text-white/40 uppercase font-mono">(${{c.role}})</span>
          <span class="truncate max-w-[110px]">${{c.headline}}</span>
        </button>
      `).join('');
    }}

    function selectCard(idx) {{
      currentIdx = idx;
      renderNav();
      const card = cards[idx];
      document.getElementById('disp-tag').innerText = `CARD 0${{idx+1}} · ${{card.role.toUpperCase()}}`;
      document.getElementById('disp-headline').innerText = card.headline;
      document.getElementById('disp-subheadline').innerText = card.subheadline;
      document.getElementById('disp-layout').innerText = card.layout;
      document.getElementById('disp-img').src = card.img;

      document.getElementById('input-headline').value = card.headline;
      document.getElementById('input-subheadline').value = card.subheadline;
      document.getElementById('input-directive').value = critiqueDirectivesByCard[card.id] || '';

      document.getElementById('slider-pitch').value = card.rotateX;
      document.getElementById('slider-yaw').value = card.rotateY;
      document.getElementById('slider-roll').value = card.rotate;
      document.getElementById('slider-scale').value = card.scale;
      document.getElementById('slider-x').value = card.x;
      document.getElementById('slider-y').value = card.y;

      update3D();
    }}

    function update3D() {{
      const rx = parseFloat(document.getElementById('slider-pitch').value);
      const ry = parseFloat(document.getElementById('slider-yaw').value);
      const r = parseFloat(document.getElementById('slider-roll').value);
      const s = parseFloat(document.getElementById('slider-scale').value);
      const x = parseFloat(document.getElementById('slider-x').value);
      const y = parseFloat(document.getElementById('slider-y').value);

      document.getElementById('val-pitch').innerText = `${{rx}}°`;
      document.getElementById('val-yaw').innerText = `${{ry}}°`;
      document.getElementById('val-roll').innerText = `${{r}}°`;
      document.getElementById('val-scale').innerText = `${{s.toFixed(2)}}x`;
      document.getElementById('val-x').innerText = `${{x}}px`;
      document.getElementById('val-y').innerText = `${{y}}px`;

      const win = document.getElementById('stage-window');
      win.style.transform = `translate3d(${{x}}px, ${{y}}px, 0) scale(${{s}}) rotate(${{r}}deg) rotateX(${{rx}}deg) rotateY(${{ry}}deg)`;

      cards[currentIdx].rotateX = rx;
      cards[currentIdx].rotateY = ry;
      cards[currentIdx].rotate = r;
      cards[currentIdx].scale = s;
      cards[currentIdx].x = x;
      cards[currentIdx].y = y;

      updatePresetButtons();
    }}

    function updatePresetButtons() {{
      const rx = parseFloat(document.getElementById('slider-pitch').value);
      const ry = parseFloat(document.getElementById('slider-yaw').value);
      const r = parseFloat(document.getElementById('slider-roll').value);
      const s = parseFloat(document.getElementById('slider-scale').value);
      const x = parseFloat(document.getElementById('slider-x').value);
      const y = parseFloat(document.getElementById('slider-y').value);

      const isHero = rx === 4 && ry === 0 && r === 0 && Math.abs(s - 1.03) < 0.005 && x === 0 && y === 25;
      const isInward = Math.abs(ry) >= 6 && rx === 4 && Math.abs(s - 1.02) < 0.005;
      const isFlat = rx === 0 && ry === 0 && r === 0 && s === 1.0 && x === 0 && y === 0;

      const activeCls = "px-2 py-0.5 text-[10px] rounded bg-indigo-500/30 text-indigo-300 border border-indigo-500/50 font-bold transition";
      const inactiveCls = "px-2 py-0.5 text-[10px] rounded bg-white/5 text-white/70 hover:bg-white/10 border border-transparent font-medium transition";

      const btnHero = document.getElementById('btn-pose-hero');
      const btnInward = document.getElementById('btn-pose-inward');
      const btnFlat = document.getElementById('btn-pose-flat');
      if (btnHero) btnHero.className = isHero ? activeCls : inactiveCls;
      if (btnInward) btnInward.className = isInward ? activeCls : inactiveCls;
      if (btnFlat) btnFlat.className = isFlat ? activeCls : inactiveCls;
    }}

    function applyPose(type) {{
      const card = cards[currentIdx];
      if (type === 'hero') {{
        document.getElementById('slider-pitch').value = 4;
        document.getElementById('slider-yaw').value = 0;
        document.getElementById('slider-roll').value = 0;
        document.getElementById('slider-scale').value = 1.03;
        document.getElementById('slider-x').value = 0;
        document.getElementById('slider-y').value = 25;
      }} else if (type === 'inward') {{
        const isRight = card.layout.includes('right');
        document.getElementById('slider-pitch').value = 4;
        document.getElementById('slider-yaw').value = isRight ? -8 : 8;
        document.getElementById('slider-roll').value = isRight ? 2 : -2;
        document.getElementById('slider-scale').value = 1.02;
        document.getElementById('slider-x').value = 0;
        document.getElementById('slider-y').value = 0;
      }} else if (type === 'flat') {{
        document.getElementById('slider-pitch').value = 0;
        document.getElementById('slider-yaw').value = 0;
        document.getElementById('slider-roll').value = 0;
        document.getElementById('slider-scale').value = 1.0;
        document.getElementById('slider-x').value = 0;
        document.getElementById('slider-y').value = 0;
      }}
      update3D();
    }}

    function resetCardPose() {{
      const orig = initialCardPoses[currentIdx];
      if (!orig) return;
      document.getElementById('slider-pitch').value = orig.rotateX;
      document.getElementById('slider-yaw').value = orig.rotateY;
      document.getElementById('slider-roll').value = orig.rotate;
      document.getElementById('slider-scale').value = orig.scale;
      document.getElementById('slider-x').value = orig.x;
      document.getElementById('slider-y').value = orig.y;
      update3D();
    }}

    function updateCopy() {{
      const h = document.getElementById('input-headline').value;
      const sh = document.getElementById('input-subheadline').value;
      document.getElementById('disp-headline').innerText = h;
      document.getElementById('disp-subheadline').innerText = sh;
      cards[currentIdx].headline = h;
      cards[currentIdx].subheadline = sh;
    }}

    function updateDirective() {{
      const val = document.getElementById('input-directive').value;
      critiqueDirectivesByCard[cards[currentIdx].id] = val;
    }}

    function buildCurrentDirectivesPayload() {{
      const card = cards[currentIdx];
      const directive = document.getElementById('input-directive').value;
      return {{
        target: target,
        locale: locale,
        card_id: card.id,
        cardId: card.id,
        role: card.role,
        directive: directive,
        notes: directive,
        patch: {{
          headline: card.headline,
          subheadline: card.subheadline,
          deviceOffset: {{
            rotateX: card.rotateX,
            rotateY: card.rotateY,
            rotate: card.rotate,
            scale: card.scale,
            x: card.x,
            y: card.y
          }}
        }}
      }};
    }}

    function buildAllDirectivesFile() {{
      const directives = {{}};
      cards.forEach(c => {{
        const userDirective = critiqueDirectivesByCard[c.id] || '';
        directives[c.id] = {{
          target: target,
          locale: locale,
          card_id: c.id,
          role: c.role,
          directive: userDirective,
          notes: userDirective,
          patch: {{
            headline: c.headline,
            subheadline: c.subheadline,
            deviceOffset: {{
              rotateX: c.rotateX,
              rotateY: c.rotateY,
              rotate: c.rotate,
              scale: c.scale,
              x: c.x,
              y: c.y
            }}
          }}
        }};
      }});
      return {{
        directives: directives,
        latest: buildCurrentDirectivesPayload()
      }};
    }}

    function downloadDirectivesJson() {{
      const fullDirectives = buildAllDirectivesFile();
      const blob = new Blob([JSON.stringify(fullDirectives, null, 2)], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'review-directives.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      const statusP = document.getElementById('sync-status');
      statusP.innerText = '✓ review-directives.json 已下载！可由 Agent 运行 apply-critique 直接吸收。';
      statusP.classList.remove('hidden');
      setTimeout(() => statusP.classList.add('hidden'), 4000);
    }}

    async function syncDirectivesToAgent() {{
      const payload = buildCurrentDirectivesPayload();
      const statusP = document.getElementById('sync-status');

      try {{
        const res = await fetch('http://localhost:3100/api/critique', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        if (res.ok) {{
          statusP.innerText = '✓ 审阅指令已实时写入 Agent 协同指令 (.creative/review-directives.json)！';
          statusP.classList.remove('hidden');
          setTimeout(() => statusP.classList.add('hidden'), 4000);
          return;
        }} else {{
          throw new Error('API 响应失败');
        }}
      }} catch (err) {{
        // Zero-server fallback: copy markdown to clipboard
        statusP.innerText = '✓ 零服务模式：审阅指令已复制到剪贴板！直接在 Agent 对话中粘贴即可。';
        statusP.classList.remove('hidden');
        copyDirectiveMarkdown();
      }}
    }}

    function copyDirectiveMarkdown() {{
      const card = cards[currentIdx];
      const directive = document.getElementById('input-directive').value;
      const md = `### Human Review Directive\\n- Target: ${{target}} | ${{locale}} | ${{card.id}} (Role: ${{card.role}})\\n- Spatial: Pitch=${{card.rotateX}}°, Yaw=${{card.rotateY}}°, Roll=${{card.rotate}}°, Scale=${{card.scale.toFixed(2)}}x, Offset=(${{card.x}}px, ${{card.y}}px)\\n- Headline: "${{card.headline}}"\\n- Subheadline: "${{card.subheadline}}"\\n- Directive: ${{directive || 'Approved current visual pose'}}`;
      navigator.clipboard.writeText(md).then(() => {{
        const statusP = document.getElementById('sync-status');
        statusP.innerText = '✓ 审阅指令 Markdown 已复制到剪贴板！';
        statusP.classList.remove('hidden');
        setTimeout(() => statusP.classList.add('hidden'), 3000);
      }}).catch(() => {{}});
    }}

    // Init
    selectCard(0);
  </script>
</body>
</html>
"""

    out_file.write_text(html_content, encoding="utf-8")

    return {
        "status": "ok",
        "path": str(out_file),
        "cards_count": len(cards_data),
        "target": chosen_target,
        "locale": chosen_locale,
    }
