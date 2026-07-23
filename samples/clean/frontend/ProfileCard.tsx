// Hardened counterpart of samples/vulnerable/frontend/ProfileCard.tsx.
import DOMPurify from 'dompurify';
import { useEffect, useState } from 'react';

interface Profile {
  id: string;
  displayName: string;
  bioHtml: string;
}

export function ProfileCard({ userId }: { userId: string }): JSX.Element {
  const [profile, setProfile] = useState<Profile | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  useEffect(() => {
    const controller = new AbortController();

    const load = async (): Promise<void> => {
      try {
        // The session cookie authenticates the call; no token is bundled.
        const response = await fetch(`/api/profile/${encodeURIComponent(userId)}`, {
          credentials: 'include',
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Profile request failed: ${response.status}`);
        }
        setProfile((await response.json()) as Profile);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : 'Unknown error');
        }
      }
    };

    void load();
    return () => controller.abort();
  }, [userId]);

  if (error !== undefined) {
    return <div role="alert">{error}</div>;
  }
  if (profile === undefined) {
    return <div>Loading…</div>;
  }

  return (
    <div className="profile-card">
      <h2>{profile.displayName}</h2>

      {/* Sanitised before it is trusted as markup. */}
      <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(profile.bioHtml) }} />

      <img src={`/avatars/${encodeURIComponent(profile.id)}.png`} alt={`${profile.displayName} avatar`} />
    </div>
  );
}
