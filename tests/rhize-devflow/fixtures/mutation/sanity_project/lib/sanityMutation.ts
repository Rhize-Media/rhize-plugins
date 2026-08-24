import { client } from '@/lib/sanity';

export async function updateArticle(id: string, patch: Record<string, unknown>) {
  return client.patch(id).set(patch).commit();
}
