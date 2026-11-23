import { useState } from 'react';
import { readHistory } from './historyRequest';

type Match = { text: string; x: number; y: number; width: number; height: number };
export function CaptureCopy({ locale, target, card, source, defaultLocale, defaultSource }: { locale: string; target: string; card: string; source: string; defaultLocale: string; defaultSource?: string }) {
  const [phrase, setPhrase] = useState('');
  const [matches, setMatches] = useState<Match[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function check() {
    setBusy(true); setMatches(undefined); setError('');
    try {
      const params = new URLSearchParams({ locale, target, card, phrase: phrase.trim() });
      setMatches((await readHistory<{ matches: Match[] }>('/api/capture-copy?' + params, 'capture text', 100000)).matches);
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  return <details className="text-xs"><summary>Review original capture text</summary>
    <div className="grid gap-2 my-2">{[[locale, source], ...(locale !== defaultLocale && defaultSource && defaultSource !== source
      ? [[defaultLocale, defaultSource]] : [])].map(([language, url]) => <a key={language} href={url} target="_blank" rel="noreferrer">
        <img className="w-full" src={url} alt={language + ' original capture'} loading="lazy" />
        <span className="underline">{language} · Open full size</span>
      </a>)}</div>
    {locale !== defaultLocale && defaultSource === source && <p>Both languages use the same capture.</p>}
    <label>Phrase to locate<input value={phrase} disabled={busy} maxLength={160}
      onChange={event => { setPhrase(event.target.value); setMatches(undefined); setError(''); }} /></label>
    <button disabled={busy || !phrase.trim()} onClick={() => void check()}>{busy ? 'Reading capture…' : 'Find phrase'}</button>
    {error && <p role="alert">{error}</p>}
    {matches && <p role="status">{matches.length} matching lines recognized.</p>}
    {!!matches?.length && <><div className="relative">
      <img className="block w-full" src={source} alt="Original capture with matching text highlighted" />
      {matches.map((box, index) => <span key={index} className="absolute border-2 border-amber-400" style={{
        left: box.x * 100 + '%', top: box.y * 100 + '%', width: box.width * 100 + '%', height: box.height * 100 + '%' }} />)}
    </div><ul>{matches.map((box, index) => <li key={index}>{box.text}</li>)}</ul></>}
  </details>;
}
