type Props = { candidateId: string; assets: Record<string, unknown> };

export function CandidatePreviewMedia({ candidateId, assets }: Props) {
  const preview = Object.hasOwn(assets, 'preview/app_preview.mp4');
  const poster = Object.hasOwn(assets, 'preview/poster.png');
  if (!preview && !poster) return null;
  const base = '/api/artifacts/' + encodeURIComponent(candidateId) + '/preview/';
  return <section aria-label="App Preview review" className="my-4 space-y-3">
    <h3 className="font-semibold">App Preview and poster</h3>
    {preview && <video aria-label="App Preview" controls preload="metadata"
      className="w-full rounded-lg" src={base + 'app_preview.mp4'}
      poster={poster ? base + 'poster.png' : undefined} />}
    {poster && <a href={base + 'poster.png'} target="_blank" rel="noreferrer">
      <img className="w-full rounded-lg" src={base + 'poster.png'} alt="App Preview poster" />
    </a>}
  </section>;
}
