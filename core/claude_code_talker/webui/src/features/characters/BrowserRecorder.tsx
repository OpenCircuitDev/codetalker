import { useEffect, useRef, useState } from "react";

const MIME_FALLBACK = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
];

function pickMime(): string {
  for (const m of MIME_FALLBACK) {
    if (typeof MediaRecorder !== "undefined" &&
        MediaRecorder.isTypeSupported &&
        MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

interface Props {
  onRecorded: (blob: Blob, mimeType: string) => void;
  maxSeconds?: number;
}

export function BrowserRecorder({ onRecorded, maxSeconds = 30 }: Props) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const tickRef = useRef<number | null>(null);

  useEffect(() => () => stopAll(), []);

  function stopAll() {
    if (tickRef.current) { window.clearInterval(tickRef.current); tickRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (recRef.current && recRef.current.state !== "inactive") recRef.current.stop();
    recRef.current = null;
  }

  async function start() {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickMime();
      const opts = mime ? { mimeType: mime } : undefined;
      const rec = new MediaRecorder(stream, opts);
      recRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || mime || "audio/webm" });
        onRecorded(blob, rec.mimeType || mime || "audio/webm");
        stopAll();
        setRecording(false);
        setElapsed(0);
      };
      rec.start();
      setRecording(true);
      tickRef.current = window.setInterval(() => {
        setElapsed((s) => {
          if (s + 1 >= maxSeconds) { stop(); return s + 1; }
          return s + 1;
        });
      }, 1000);
    } catch (e: any) {
      setError(e?.message || "microphone access denied");
    }
  }

  function stop() {
    if (recRef.current && recRef.current.state !== "inactive") recRef.current.stop();
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {!recording ? (
          <button onClick={start} className="px-3 py-1 bg-rose-600 text-white rounded">Record</button>
        ) : (
          <button onClick={stop} className="px-3 py-1 bg-zinc-600 text-white rounded">Stop</button>
        )}
        <span className="text-sm text-zinc-400">{elapsed}s / {maxSeconds}s</span>
      </div>
      {error && <p className="text-rose-400 text-sm">{error}</p>}
    </div>
  );
}
