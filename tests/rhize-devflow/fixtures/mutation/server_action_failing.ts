'use server'

import { supabase } from '@/lib/supabase'

export async function deletePlayer(id) {
  const result = await supabase.from('players').delete().eq('id', id)
  return result
}
