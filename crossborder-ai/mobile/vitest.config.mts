import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text"],
      include: [
        "src/features/function-hub/catalog.ts",
        "src/features/activity/notification-groups.ts",
        "src/features/account/account-labels.ts",
        "src/design/auth-layout.ts",
        "src/features/query-state/query-state.ts",
        "src/features/time/timezone.ts",
        "src/features/commerce/channel-selection.ts",
        "src/features/library/library-order.ts",
        "src/features/notifications/preference-form.ts",
        "src/features/media/video-save.ts",
      ],
    },
  },
});
