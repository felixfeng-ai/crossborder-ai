import { router, useLocalSearchParams } from "expo-router";
import { useEffect } from "react";

export default function NotificationTaskRedirect() {
  const params = useLocalSearchParams<{
    taskId: string;
    workspaceId?: string;
  }>();

  useEffect(() => {
    const taskId = typeof params.taskId === "string" ? params.taskId : "";
    if (!taskId) {
      router.replace("/");
      return;
    }
    router.replace({
      pathname: "/task/[workItemId]",
      params: {
        workItemId: taskId,
        workspaceId: params.workspaceId ?? "",
      },
    });
  }, [params.taskId, params.workspaceId]);

  return null;
}
