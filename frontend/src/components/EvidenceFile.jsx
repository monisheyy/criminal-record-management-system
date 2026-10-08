import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Download, Upload } from 'lucide-react';
import { casesAPI, getErrorMessage, saveBlob } from '../services/api';

const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif,application/pdf';
const MAX_BYTES = 20 * 1024 * 1024;

const formatSize = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

/**
 * The stored file for one evidence item. Files are write-once: once attached
 * they can be downloaded (the API re-checks the SHA-256 first) but never replaced.
 */
export default function EvidenceFile({ caseId, evidence, canWrite, onUploaded }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_BYTES) {
      toast.error('Evidence files must be 20 MB or smaller.');
      return;
    }
    setBusy(true);
    try {
      await casesAPI.uploadEvidenceFile(caseId, evidence.id, file);
      toast.success('File stored and added to the chain of custody.');
      onUploaded();
    } catch (err) {
      toast.error(getErrorMessage(err, 'Upload failed.'));
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setBusy(true);
    try {
      saveBlob(await casesAPI.evidenceFile(caseId, evidence.id), evidence.file_name || 'evidence');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Download failed.'));
    } finally {
      setBusy(false);
    }
  };

  if (evidence.file_content_type) {
    return (
      <div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={download} disabled={busy}
          title={`SHA-256 ${evidence.file_sha256}`}>
          <Download size={12} aria-hidden="true" /> {busy ? 'Checking…' : 'Download'}
        </button>
        <div className="td-sub">{evidence.file_name} · {formatSize(evidence.file_size)}</div>
      </div>
    );
  }
  if (!canWrite) return <span className="td-sub">No file</span>;
  return (
    <>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => input.current?.click()} disabled={busy}>
        <Upload size={12} aria-hidden="true" /> {busy ? 'Uploading…' : 'Attach file'}
      </button>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={upload} aria-label={`Attach a file to ${evidence.evidence_number}`} />
      {evidence.file_sha256 && <div className="td-sub">Must match the recorded hash</div>}
    </>
  );
}
