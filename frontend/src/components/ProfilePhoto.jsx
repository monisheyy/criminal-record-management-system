import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Camera, Trash2 } from 'lucide-react';
import { criminalPhotoUrl, criminalsAPI, getErrorMessage } from '../services/api';
import { ConfirmDialog } from './ui';

const ACCEPT = 'image/jpeg,image/png,image/webp';
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * Offender photo with add / replace / remove controls. The API stores the
 * file write-once under its SHA-256 and records every change in the audit trail.
 */
export default function ProfilePhoto({ profile, initials, onChange }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [failed, setFailed] = useState('');

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_BYTES) {
      toast.error('Photos must be 5 MB or smaller.');
      return;
    }
    setBusy(true);
    try {
      const res = await criminalsAPI.uploadPhoto(profile.id, file);
      onChange(res.data);
      toast.success(profile.photo_sha256 ? 'Photo replaced.' : 'Photo added.');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Photo upload failed.'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (reason) => {
    try {
      const res = await criminalsAPI.removePhoto(profile.id, reason);
      onChange(res.data);
      setConfirming(false);
      toast.success('Photo removed.');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Could not remove the photo.'));
    }
  };

  const hasPhoto = !!profile.photo_sha256 && failed !== profile.photo_sha256;
  return (
    <div className="profile-photo-wrap">
      {hasPhoto ? (
        <img className="profile-photo" src={criminalPhotoUrl(profile.id, profile.photo_sha256)}
          alt={`Photo of ${profile.first_name} ${profile.last_name}`} onError={() => setFailed(profile.photo_sha256)} />
      ) : (
        <div className="dossier-avatar" aria-hidden="true">{initials}</div>
      )}
      <div className="profile-photo-actions">
        <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()} disabled={busy}>
          <Camera size={12} aria-hidden="true" /> {busy ? 'Uploading…' : profile.photo_sha256 ? 'Replace' : 'Add photo'}
        </button>
        {profile.photo_sha256 && (
          <button type="button" className="btn btn-secondary btn-icon" aria-label="Remove photo" onClick={() => setConfirming(true)}>
            <Trash2 size={12} aria-hidden="true" />
          </button>
        )}
      </div>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={upload} aria-label="Choose a photo" />
      {confirming && (
        <ConfirmDialog title="Remove photo" danger requireReason confirmLabel="Remove photo"
          message="The photo will no longer be shown on this record. The file itself is kept so the audit trail can still prove what was on record."
          onConfirm={remove} onCancel={() => setConfirming(false)} />
      )}
    </div>
  );
}
