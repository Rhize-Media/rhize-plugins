'use server';

import { z } from 'zod';
import { revalidateTag } from 'next/cache';
import { supabase } from '@/lib/supabase';

const PlayerUpdateSchema = z.object({ name: z.string() });

export async function updatePlayer(id: string, data: unknown) {
  const parsed = PlayerUpdateSchema.parse(data);
  try {
    const { error } = await supabase.from('players').update(parsed).eq('id', id);
    if (error) {
      throw new Error(error.message);
    }
    revalidateTag('players');
    return { success: true };
  } catch (error) {
    throw error;
  }
}
