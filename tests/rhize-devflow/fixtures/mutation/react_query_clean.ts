import { useMutation } from '@tanstack/react-query';
import { playerKeys } from './player-keys';
import { toast } from 'sonner';

interface UpdatePlayerInput {
  id: string;
  name: string;
}

export function useUpdatePlayer() {
  return useMutation({
    mutationFn: (data: UpdatePlayerInput) => updatePlayerApi(data),
    onMutate: async (data: UpdatePlayerInput) => {
      return { previous: data };
    },
    onError: (error, variables, context) => {
      toast.error('Update failed');
      if (context?.previous) {
        console.log(context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries(playerKeys.all);
    },
  });
}
