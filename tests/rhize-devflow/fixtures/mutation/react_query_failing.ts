import { useMutation } from '@tanstack/react-query';

export function useCreateGame() {
  return useMutation({
    mutationFn: (data) => createGameApi(data),
  });
}
