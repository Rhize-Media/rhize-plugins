import type { CollectionConfig } from 'payload/types';
import { revalidateTag } from 'next/cache';

export const Teams: CollectionConfig = {
  slug: 'teams',
  hooks: {
    beforeChange: [
      ({ data }) => {
        if (!data.name) {
          throw new Error('name is required');
        }
        return data;
      },
    ],
    afterChange: [
      ({ doc }) => {
        revalidateTag('teams');
      },
    ],
    afterDelete: [
      ({ doc }) => {
        revalidateTag('teams');
      },
    ],
  },
};
