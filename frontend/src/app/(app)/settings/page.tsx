'use client';

import { useEffect, useState, type FormEvent } from 'react';

import { Alert, Button, Card, Field, Select, Spinner } from '@/components/ui/primitives';
import { ApiError, api } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { SEVERITY_LABEL, SEVERITY_ORDER } from '@/lib/display';
import type { Capabilities } from '@/lib/types';

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [capabilities, setCapabilities] = useState<Capabilities | undefined>(undefined);
  const [model, setModel] = useState(user?.preferences.llm_model ?? '');
  const [minSeverity, setMinSeverity] = useState(user?.preferences.min_severity ?? 'low');
  const [githubToken, setGithubToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  useEffect(() => {
    void api
      .capabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(undefined));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(undefined);
    setError(undefined);

    try {
      await api.updatePreferences({
        llm_model: model,
        min_severity: minSeverity,
        // Only send the token when the user typed one; an empty field means
        // "leave it alone", not "clear it".
        ...(githubToken !== '' ? { github_token: githubToken } : {}),
      });
      await refreshUser();
      setGithubToken('');
      setMessage('Ayarlar kaydedildi.');
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Kaydedilemedi.');
    } finally {
      setSaving(false);
    }
  }

  async function handleClearToken() {
    setSaving(true);
    try {
      await api.updatePreferences({ github_token: '' });
      await refreshUser();
      setMessage('GitHub token silindi.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-title">Ayarlar</h1>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        {message !== undefined && <Alert tone="success">{message}</Alert>}
        {error !== undefined && <Alert>{error}</Alert>}

        <Card className="flex flex-col gap-4 p-4">
          <h2 className="text-eyebrow">Model</h2>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="model" className="text-sm font-medium">
              İnceleme modeli
            </label>
            <Select
              id="model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            >
              <option value="">
                Sunucu varsayılanı
                {capabilities !== undefined && ` (${capabilities.default_model})`}
              </option>
              {capabilities?.available_models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
            <p className="text-muted text-xs">
              {capabilities?.ollama_reachable === false
                ? 'Ollama’ya ulaşılamıyor; model listesi boş.'
                : 'Yerel Ollama üzerinde kurulu modeller listelenir.'}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="severity" className="text-sm font-medium">
              Gösterilecek en düşük önem derecesi
            </label>
            <Select
              id="severity"
              value={minSeverity}
              onChange={(event) => setMinSeverity(event.target.value)}
            >
              {SEVERITY_ORDER.map((severity) => (
                <option key={severity} value={severity}>
                  {SEVERITY_LABEL[severity]}
                </option>
              ))}
            </Select>
          </div>
        </Card>

        <Card className="flex flex-col gap-3 p-4">
          <h2 className="text-eyebrow">GitHub</h2>
          <Field
            label="Kişisel erişim token'ı"
            name="github_token"
            type="password"
            autoComplete="off"
            value={githubToken}
            onChange={(event) => setGithubToken(event.target.value)}
            placeholder={user?.has_github_token === true ? '•••••• (kayıtlı)' : 'ghp_…'}
            hint="Özel repoların pull request'lerini incelemek için gerekir. Sunucuda Fernet ile şifrelenmiş saklanır, hiçbir yerde geri gösterilmez."
          />
          {user?.has_github_token === true && (
            <div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={saving}
                onClick={() => void handleClearToken()}
              >
                Kayıtlı token’ı sil
              </Button>
            </div>
          )}
        </Card>

        {capabilities !== undefined && (
          <Card className="p-4">
            <h2 className="text-eyebrow">Etkin statik analiz araçları</h2>
            <p className="text-muted mt-2 text-xs">
              Ajan bulguları yalnızca bu araçlarla çapraz doğrulanabilir.
            </p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {capabilities.static_analysers.map((tool) => (
                <li
                  key={tool}
                  className="bg-verified-soft text-verified border-verified-ring rounded-md border px-2 py-0.5 font-mono text-xs"
                >
                  {tool}
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving && <Spinner />}
            Kaydet
          </Button>
        </div>
      </form>
    </div>
  );
}
