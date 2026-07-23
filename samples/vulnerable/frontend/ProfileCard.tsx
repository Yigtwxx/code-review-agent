// Deliberately vulnerable React component used as a review fixture.
// DO NOT SHIP. Each defect is marked by the comment above it.
import React, { useEffect, useState } from 'react';

// Secret bundled into client-side JavaScript, readable by anyone.
const SEGMENT_WRITE_KEY = 'AIzaSyEXAMPLEFIXTURENOTAREALKEY000000000';
const ADMIN_API_TOKEN = 'ghp_EXAMPLEFIXTURENOTAREALTOKEN0000000000';

interface Profile {
  id: string;
  displayName: string;
  bioHtml: string;
}

export function ProfileCard({ userId }: { userId: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [note, setNote] = useState('');

  useEffect(() => {
    // No error handling and no cleanup: a unmounted component still sets state.
    fetch('/api/profile/' + userId, {
      headers: { Authorization: `Bearer ${ADMIN_API_TOKEN}` },
    })
      .then((r) => r.json())
      .then((data) => setProfile(data));
  }, [userId]);

  const runNote = () => {
    // Remote code execution in the browser from user-controlled text.
    return eval(note);
  };

  if (!profile) return <div>Loading…</div>;

  return (
    <div className="profile-card">
      <h2>{profile.displayName}</h2>

      {/* Stored XSS: server-supplied HTML injected without sanitisation. */}
      <div dangerouslySetInnerHTML={{ __html: profile.bioHtml }} />

      <a href={`javascript:alert('${profile.displayName}')`}>Greet</a>

      <input value={note} onChange={(e) => setNote(e.target.value)} />
      <button onClick={runNote}>Run</button>

      {/* No accessible name; screen readers announce nothing useful. */}
      <img src={`/avatars/${profile.id}.png`} />
    </div>
  );
}
