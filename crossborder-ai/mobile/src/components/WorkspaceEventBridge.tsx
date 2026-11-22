import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { PREVIEW_MODE } from "@/api/client";
import { subscribeWorkspaceEvents } from "@/api/events";
import { useAuthStore } from "@/stores/auth";
import { useWorkspaceStore } from "@/stores/workspace";

export function WorkspaceEventBridge() {
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.token);
  const workspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);

  useEffect(() => {
    if (!token || !workspaceId || PREVIEW_MODE) return;
    return subscribeWorkspaceEvents({
      token,
      workspaceId,
      onEvent: (event) => {
        void queryClient.invalidateQueries({
          queryKey: ["mobile", "timeline", workspaceId],
        });
        if (event.work_item_id) {
          void queryClient.invalidateQueries({
            queryKey: [
              "mobile",
              "work-item",
              workspaceId,
              event.work_item_id,
            ],
          });
        }
      },
    });
  }, [queryClient, token, workspaceId]);

  return null;
}
