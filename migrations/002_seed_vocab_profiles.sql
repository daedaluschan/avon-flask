INSERT INTO vocab_profiles (profile_key, display_name, is_guest, is_default)
VALUES
  ('jinny', 'Jinny', FALSE, TRUE),
  ('dd',    'DD',    FALSE, FALSE),
  ('guest', 'Guest', TRUE,  FALSE)
ON CONFLICT (profile_key) DO UPDATE
SET
  display_name = EXCLUDED.display_name,
  is_guest     = EXCLUDED.is_guest,
  is_default   = EXCLUDED.is_default,
  updated_at   = NOW();
