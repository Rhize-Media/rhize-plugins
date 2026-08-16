import { supabase } from '@/lib/supabase';

export async function upsertPlayer(id: string, payload: Record<string, unknown>) {
  const { data, error } = await supabase.from('players').upsert(payload);
  if (error) {
    throw new Error(error.message);
  }
  return data;
}
