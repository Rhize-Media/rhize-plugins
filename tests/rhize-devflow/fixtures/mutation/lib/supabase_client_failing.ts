import { supabase } from '@/lib/supabase';

export async function upsertGame(id, payload) {
  const result = await supabase.from('games').upsert(payload);
  return result;
}
