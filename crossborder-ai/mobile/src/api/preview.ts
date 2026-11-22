import type {
  BootstrapResponse,
  CommandResponse,
  TimelineResponse,
  WorkItemDetail,
} from "./types";
import { setClockAnchor } from "../features/time/clock";

/**
 * 预览固定锚定在「今天 10:30」这个业务时刻。
 *
 * 这样 09:42→13:42 的窗口刚好落在「现在」里：剩余时长为 3 小时 12 分，
 * 时间轴圆点在 20% 处，凌晨或深夜截图都不会出现未来时间。
 * 这里必须用本地日期，不能用 toISOString —— UTC 日期会让首页和计划页差一天。
 */
const previewAnchor = new Date();
previewAnchor.setHours(10, 30, 0, 0);

const businessDate = [
  previewAnchor.getFullYear(),
  String(previewAnchor.getMonth() + 1).padStart(2, "0"),
  String(previewAnchor.getDate()).padStart(2, "0"),
].join("-");

const previewAnchorMs = previewAnchor.getTime();

const primaryId = "11111111-1111-4111-8111-111111111111";
const reviewId = "22222222-2222-4222-8222-222222222222";
const doneId = "33333333-3333-4333-8333-333333333333";
const mediaId = "44444444-4444-4444-8444-444444444444";
const failedMediaId = "55555555-5555-4555-8555-555555555555";
const listingId = "66666666-6666-4666-8666-666666666666";
const inventoryId = "77777777-7777-4777-8777-777777777777";
const refundId = "88888888-8888-4888-8888-888888888888";

function isoAt(hour: number, minute: number) {
  const value = new Date(previewAnchor);
  value.setHours(hour, minute, 0, 0);
  return value.toISOString();
}

function previewActionRun(input: {
  actionId: string;
  platform: string;
  targetType: string;
  targetId: string;
  riskLevel: "medium" | "high";
  occurredAt: string;
  policyReason: string;
}) {
  return {
    id: "77777777-7777-4777-8777-777777777777",
    action_id: input.actionId,
    platform: input.platform,
    target_type: input.targetType,
    target_id: input.targetId,
    status: "awaiting_confirmation",
    risk_level: input.riskLevel,
    autonomy_level: "confirm",
    policy_reason: input.policyReason,
    requires_dual_approval: false,
    attempt: 0,
    external_id: null,
    error_code: null,
    created_at: input.occurredAt,
    started_at: null,
    finished_at: null,
  };
}

export function getPreviewBootstrap(): BootstrapResponse {
  // 预览数据被请求即可确定「处于预览模式」，把时钟锚定到业务时刻。
  setClockAnchor(previewAnchorMs);
  return {
    user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    display_name: "Felix",
    contract_version: "1",
    workspaces: [
      {
        id: "99999999-9999-4999-8999-999999999999",
        name: "Felix 的工作区",
        type: "personal",
        role: "owner",
      },
    ],
  };
}

export function getPreviewTimeline(): TimelineResponse {
  setClockAnchor(previewAnchorMs);
  return {
    business_date: businessDate,
    next_cursor: null,
    items: [
      {
        id: primaryId,
        kind: "order_exception",
        title: "两个订单\n四小时后超时",
        summary: "供应商尚未揽收，买家说明已写好。",
        status: "waiting_user",
        priority: "urgent",
        current_step: "等待你决定",
        requires_action: "confirm",
        version: 1,
        // 与标题「09:42 起四小时后超时」自洽：13:42 截止。
        due_at: isoAt(13, 42),
        occurred_at: isoAt(9, 42),
        commerce: {
          amount: "1284.00",
          currency: "CNY",
          order_count: 2,
          thumbnails: [],
        },
      },
      {
        id: reviewId,
        kind: "customer_reply",
        title: "一条评价等待回复",
        summary: "回复草稿已写好。",
        status: "waiting_user",
        priority: "attention",
        current_step: "等待你决定",
        requires_action: "confirm",
        version: 2,
        due_at: isoAt(18, 0),
        // 锚点 10:30 → 「4 小时前」，与设计稿该行的相对时间一致。
        occurred_at: isoAt(6, 30),
      },
      {
        id: doneId,
        kind: "inventory_update",
        title: "3 个 SKU 库存已同步",
        summary: "Shopify 与本地库存一致。",
        status: "succeeded",
        priority: "normal",
        current_step: "已完成",
        requires_action: "none",
        version: 1,
        due_at: null,
        // 设计稿里这行同样是「12 分钟前」。
        occurred_at: isoAt(10, 18),
      },
      {
        id: listingId,
        kind: "listing_action",
        title: "新品 Listing 已准备",
        summary: "标题、卖点和 6 张图已生成。",
        status: "waiting_user",
        priority: "attention",
        current_step: "等待你确认发布",
        requires_action: "confirm",
        version: 1,
        due_at: isoAt(16, 0),
        // 锚点 10:30 → 「12 分钟前」。
        occurred_at: isoAt(10, 18),
        commerce: {
          amount: null,
          currency: null,
          order_count: null,
          // 预览用 160px 同源静态图：走 CDN 原图 2.4MB，截图时还没下载完就是空白块。
          thumbnails: [
            "/preview/thumbs/earbuds.jpg",
            "/preview/thumbs/bottle.jpg",
            "/preview/thumbs/plant.jpg",
          ],
        },
      },
      {
        id: inventoryId,
        kind: "inventory_action",
        title: "低库存 SKU 需要补货",
        summary: "2 个 SKU 低于安全库存，建议补货 48 件。",
        status: "waiting_user",
        priority: "attention",
        current_step: "等待你确认库存调整",
        requires_action: "confirm",
        version: 1,
        due_at: isoAt(17, 30),
        occurred_at: isoAt(11, 12),
      },
      {
        id: refundId,
        kind: "refund_action",
        title: "一笔退款申请等待确认",
        summary: "商品破损，Agent 已核对订单和可退金额。",
        status: "waiting_user",
        priority: "attention",
        current_step: "等待你确认退款",
        requires_action: "confirm",
        version: 1,
        due_at: isoAt(19, 0),
        occurred_at: isoAt(11, 36),
      },
    ],
  };
}

export function getPreviewDailyPlan() {
  setClockAnchor(previewAnchorMs);
  return {
    business_date: businessDate,
    status: "active",
    overview: "今天有 1 件事需要你决定",
    decision_count: 1,
    auto_count: 1,
    monitor_count: 1,
    carryover_count: 0,
    items: [
      {
        id: "plan-decision-1",
        work_item_id: primaryId,
        title: "两个订单\n四小时后超时",
        category: "decision",
        priority_score: 130,
        reason: "供应商尚未揽收，买家说明已写好。",
        expected_action: "等待你确认后由 Agent 执行",
        status: "planned",
      },
      {
        id: "plan-auto-1",
        work_item_id: doneId,
        title: "同步 3 个 SKU 库存",
        category: "auto",
        priority_score: 20,
        reason: "Shopify 与本地库存存在差异。",
        expected_action: "Agent 正在自动处理",
        // 对应的 work item 已经是 succeeded，计划项状态必须自洽，否则会显示「待开始」。
        status: "completed",
      },
      {
        id: "plan-monitor-1",
        work_item_id: reviewId,
        title: "持续观察评价回复",
        category: "monitor",
        priority_score: 60,
        reason: "差评回复需要持续观察买家反馈。",
        expected_action: "Agent 持续观察，有变化时再提醒",
        status: "planned",
      },
    ],
  };
}

export function getPreviewNotifications() {
  return [
    {
      id: "notification-1",
      notification_type: "needs_action",
      title: "有一件事需要你决定",
      body: "打开 VeyaShip 查看 Agent 准备好的处理方案。",
      deep_link: `/t/${primaryId}?workspaceId=99999999-9999-4999-8999-999999999999`,
      work_item_id: primaryId,
      status: "sent",
      created_at: isoAt(9, 42),
      read_at: null,
    },
    {
      id: "notification-2",
      notification_type: "morning_brief",
      title: "今日计划已生成",
      body: "今天有 1 件事需要你决定",
      deep_link:
        "/plan?workspaceId=99999999-9999-4999-8999-999999999999",
      work_item_id: null,
      status: "sent",
      created_at: isoAt(8, 0),
      read_at: null,
    },
  ];
}

export function getPreviewAgentTurn(_turnId: string) {
  return {
    agent_turn_id: _turnId,
    status: "succeeded",
    input_type: "text",
    text: "帮我看看今天的订单，有超时的先处理。",
    task_status: "succeeded",
    result_summary: "已找到 2 个即将超时的订单，并准备好延迟说明和履约方案。",
    error: null,
    steps: [
      { label: "理解你的指令", status: "completed" },
      { label: "检查今天订单和物流状态", status: "completed" },
      { label: "整理需要你决定的事项", status: "completed" },
    ],
    created_work_item_ids: [primaryId],
  };
}

export function getPreviewWorkItem(workItemId: string): WorkItemDetail {
  // 这些固定任务用于预览高风险业务流的真实页面密度与确认面板。
  if (workItemId === listingId) {
    const occurredAt = isoAt(10, 40);
    return {
      id: listingId,
      version: 1,
      kind: "listing_action",
      title: "新品收纳包\n等待发布",
      summary: "标题、卖点与 6 张商品图已准备，确认后由 Agent 发布到 Shopify。",
      status: "waiting_user",
      priority: "attention",
      current_step: "等待你确认发布",
      requires_action: "confirm",
      available_actions: [
        {
          id: "primary",
          kind: "confirm",
          label: "发布商品",
          risk: "high",
          expires_at: isoAt(16, 0),
        },
      ],
      action_runs: [
        previewActionRun({
          actionId: "listings.publish",
          platform: "shopify",
          targetType: "product",
          targetId: "preview-listing-1",
          riskLevel: "high",
          occurredAt,
          policyReason: "商品发布属于高影响动作，需要你确认后写入平台。",
        }),
      ],
      action_preview: {
        action_id: "listings.publish",
        platform: "shopify",
        target_type: "product",
        target_id: "preview-listing-1",
        title: "即将发布商品",
        description: "确认后在 Shopify 创建商品、变体和媒体，并回读平台结果。",
        risk: "high",
        fields: [
          { label: "商品", value: "轻量旅行收纳包", emphasis: true },
          { label: "变体", value: "3 个" },
          { label: "图片", value: "6 张" },
          { label: "店铺", value: "veyaship.myshopify.com" },
        ],
        warning: "该操作会真实写入平台，提交后不能在这里直接撤销。",
      },
      result: null,
      customer_context: null,
      media_result: null,
      due_at: isoAt(16, 0),
      expires_at: isoAt(16, 0),
      created_at: occurredAt,
      updated_at: occurredAt,
    };
  }

  if (workItemId === inventoryId) {
    const occurredAt = isoAt(11, 12);
    return {
      id: inventoryId,
      version: 1,
      kind: "inventory_action",
      title: "低库存 SKU\n等待补货",
      summary: "2 个 SKU 低于安全库存，Agent 建议把可用库存补到 48 件。",
      status: "waiting_user",
      priority: "attention",
      current_step: "等待你确认库存调整",
      requires_action: "confirm",
      available_actions: [
        {
          id: "primary",
          kind: "confirm",
          label: "更新库存",
          risk: "medium",
          expires_at: isoAt(17, 30),
        },
      ],
      action_runs: [
        previewActionRun({
          actionId: "inventory.update",
          platform: "shopify",
          targetType: "variant",
          targetId: "preview-variant-702",
          riskLevel: "medium",
          occurredAt,
          policyReason: "库存会影响可售状态，Agent 保留最后一次人工确认。",
        }),
      ],
      action_preview: {
        action_id: "inventory.update",
        platform: "shopify",
        target_type: "variant",
        target_id: "preview-variant-702",
        title: "即将更新库存",
        description: "确认后写回 Shopify 库存地点，并回读实际可用库存。",
        risk: "medium",
        fields: [
          { label: "SKU", value: "VYA-STORAGE-02", emphasis: true },
          { label: "当前库存", value: "6 件" },
          { label: "调整后", value: "48 件", emphasis: true },
          { label: "库存地点", value: "US West" },
        ],
        warning: "库存更新会写入真实店铺，请确认补货数量和地点。",
      },
      result: null,
      customer_context: null,
      media_result: null,
      due_at: isoAt(17, 30),
      expires_at: isoAt(17, 30),
      created_at: occurredAt,
      updated_at: occurredAt,
    };
  }

  if (workItemId === refundId) {
    const occurredAt = isoAt(11, 36);
    return {
      id: refundId,
      version: 1,
      kind: "refund_action",
      title: "破损商品退款\n等待你确认",
      summary: "订单 #9102 申请部分退款，Agent 已核对平台可退余额。",
      status: "waiting_user",
      priority: "attention",
      current_step: "等待你确认退款",
      requires_action: "confirm",
      available_actions: [
        {
          id: "primary",
          kind: "confirm",
          label: "发起退款",
          risk: "high",
          expires_at: isoAt(19, 0),
        },
      ],
      action_runs: [
        previewActionRun({
          actionId: "refunds.create",
          platform: "shopify",
          targetType: "order",
          targetId: "9102",
          riskLevel: "high",
          occurredAt,
          policyReason: "退款会真实产生资金动作，必须由你确认。",
        }),
      ],
      action_preview: {
        action_id: "refunds.create",
        platform: "shopify",
        target_type: "order",
        target_id: "9102",
        title: "即将发起退款",
        description: "确认后创建真实退款交易，并回读订单退款状态。",
        risk: "high",
        fields: [
          { label: "订单", value: "#9102", emphasis: true },
          { label: "退款金额", value: "USD 30.00", emphasis: true },
          { label: "原因", value: "商品破损" },
        ],
        warning: "退款提交后无法在 App 内直接撤销。",
      },
      result: null,
      customer_context: null,
      media_result: null,
      due_at: isoAt(19, 0),
      expires_at: isoAt(19, 0),
      created_at: occurredAt,
      updated_at: occurredAt,
    };
  }

  if (workItemId === mediaId || workItemId === failedMediaId) {
    const failed = workItemId === failedMediaId;
    return {
      id: workItemId,
      version: failed ? 2 : 1,
      kind: "agent_action",
      title: failed ? "素材生成失败" : "三张商品场景图已生成",
      summary: failed
        ? "本次生成未完成，可以按下方建议重试。"
        : "主图、细节图和生活方式场景图已经准备好，可以直接用于商品素材。",
      status: failed ? "waiting_user" : "succeeded",
      priority: "normal",
      current_step: failed ? "失败" : "素材已生成并核验",
      requires_action: failed ? "retry" : "none",
      available_actions: failed
        ? [
            {
              id: "primary",
              kind: "retry",
              label: "重新生成",
              risk: "medium",
              expires_at: null,
            },
          ]
        : [],
      action_runs: [
        {
          id: "77777777-7777-4777-8777-777777777777",
          action_id: "media.generate_image",
          platform: "internal",
          target_type: "media_task",
          target_id: "preview-media-task",
          status: failed ? "retryable_failed" : "succeeded",
          risk_level: "medium",
          autonomy_level: "confirm",
          attempt: failed ? 1 : 0,
          external_id: "preview-media-task",
          error_code: failed ? "media_task_failed" : null,
          created_at: isoAt(10, 12),
          started_at: isoAt(10, 13),
          finished_at: failed ? isoAt(10, 14) : isoAt(10, 16),
        },
      ],
      action_preview: null,
      result: {
        summary: failed
          ? "图片服务暂时没有返回可用结果。"
          : "已生成 3 张可用于商品详情与广告投放的场景图。",
      },
      customer_context: null,
      media_result: {
        media_type: "image",
        task_id: workItemId,
        task_status: failed ? "failed" : "completed",
        prompt: "轻量旅行收纳包，户外自然光商品场景图",
        reference_assets: [],
        images: failed
          ? []
          : [
              "https://images.unsplash.com/photo-1556228578-8c89e6adf883?auto=format&fit=crop&w=1000&q=85",
              "https://images.unsplash.com/photo-1556228720-195a672e8a03?auto=format&fit=crop&w=1000&q=85",
              "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=1000&q=85",
            ],
        video_url: null,
        error: failed ? "图片服务暂时不可用，请稍后重新生成。" : null,
        can_retry: failed,
      },
      due_at: null,
      expires_at: null,
      created_at: isoAt(10, 12),
      updated_at: isoAt(10, 16),
    };
  }
  const source =
    workItemId === reviewId
      ? {
          id: reviewId,
          kind: "customer_reply",
          title: "一条评价等待回复",
          summary: "买家反馈物流太慢，Agent 已根据实际送达时间生成回复。",
          priority: "attention",
          version: 2,
          dueAt: isoAt(18, 0),
          occurredAt: isoAt(10, 18),
        }
      : {
          id: primaryId,
          kind: "order_exception",
          title: "两个订单\n四小时后超时",
          summary: "供应商尚未揽收，买家说明已写好。",
          priority: "urgent",
          version: 1,
          dueAt: isoAt(13, 42),
          occurredAt: isoAt(9, 42),
        };
  const isCustomerReply = source.kind === "customer_reply";
  // 已完成态单独跑一条，否则详情页的「已完成」分支永远没有数据可验。
  const isDone = workItemId === doneId;
  return {
    id: source.id,
    version: source.version,
    kind: source.kind,
    title: source.title,
    summary: source.summary,
    status: isDone ? "completed" : "waiting_user",
    priority: source.priority,
    current_step: isDone ? "已完成" : "等待你决定",
    requires_action: isDone
      ? "none"
      : isCustomerReply
        ? "choose"
        : "confirm",
    available_actions: isDone
      ? []
      : [
      {
        id: "primary",
        kind: isCustomerReply ? "choose" : "confirm",
        label:
          isCustomerReply
            ? "选择正确订单"
            : "处理这 2 个订单",
        risk: source.priority === "urgent" ? "high" : "medium",
        expires_at: source.dueAt,
      },
    ],
    action_runs: isCustomerReply ? [] : [
      {
        id: "77777777-7777-4777-8777-777777777777",
        action_id:
          source.kind === "customer_reply"
            ? "messages.reply"
            : "orders.delay_notice",
        platform: source.kind === "customer_reply" ? "email" : "shopify",
        target_type:
          source.kind === "customer_reply"
            ? "conversation"
            : "order",
        target_id: source.id,
        status: isDone ? "completed" : "awaiting_confirmation",
        risk_level: source.priority === "urgent" ? "high" : "medium",
        autonomy_level: "confirm",
        attempt: 0,
        external_id: null,
        error_code: null,
        created_at: source.occurredAt,
        started_at: isDone ? source.occurredAt : null,
        finished_at: isDone ? isoAt(10, 16) : null,
      },
    ],
    action_preview:
      isDone || isCustomerReply
        ? null
        : {
            action_id: "orders.delay_notice",
            platform: "shopify",
            target_type: "order",
            target_id: source.id,
            title: "即将处理两个超时订单",
            description: "确认后发送延迟说明并同步履约状态。",
            risk: "high",
            fields: [
              { label: "订单", value: "#1284、#1285", emphasis: true },
              { label: "动作", value: "延迟说明与履约提醒" },
            ],
            warning: "该操作会真实通知买家，提交后不能在这里直接撤销。",
          },
    result: isDone
      ? {
          summary: "延迟说明已发送，买家已收到新的送达时间。",
          orders: [
            { order_name: "#1264", product: "无线降噪耳机", status: "已更新" },
            { order_name: "#1285", product: "便携咖啡杯", status: "已更新" },
          ],
          amount: "48.00",
          currency: "USD",
        }
      : isCustomerReply
        ? null
        : {
            commerce: {
              amount: "1284.00",
              currency: "CNY",
              order_count: 2,
              thumbnails: [],
            },
          },
    customer_context:
      source.kind === "customer_reply"
        ? {
            thread_id: "88888888-8888-4888-8888-888888888888",
            subject: "Where is my order?",
            customer_message:
              "Could you tell me when my parcel will arrive?",
            draft_id: null,
            draft_version: null,
            draft_text: null,
            draft_status: null,
            language: "en",
            intent: "shipping",
            risk_level: "low",
            auto_reply_candidate: true,
            requires_human: false,
            assigned_to_me: false,
            attachments: [
              {
                id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                file_name: "parcel-photo.jpg",
                content_type: "image/jpeg",
                file_size: 184320,
                url: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1200&q=85",
              },
            ],
            order: null,
            order_candidates: [
              {
                shopify_channel_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                external_order_id: "1001",
                order_name: "#1001",
                financial_status: "paid",
                fulfillment_status: "fulfilled",
                order_created_at: isoAt(14, 10),
                tracking_company: "UPS",
                tracking_number: "1Z999",
                tracking_url: "https://tracking.example.com/1Z999",
                product_title: "无线降噪耳机",
                total_price: "30.00",
                currency: "USD",
              },
              {
                shopify_channel_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                external_order_id: "1002",
                order_name: "#1002",
                financial_status: "paid",
                fulfillment_status: "partial",
                order_created_at: isoAt(15, 8),
                tracking_company: "DHL",
                tracking_number: "DHL123",
                tracking_url: "https://tracking.example.com/DHL123",
                product_title: "便携咖啡杯",
                total_price: "18.00",
                currency: "USD",
              },
            ],
          }
        : null,
    media_result: null,
    due_at: source.dueAt,
    expires_at: source.dueAt,
    created_at: source.occurredAt,
    updated_at: source.occurredAt,
  };
}

export async function previewCommand(): Promise<CommandResponse> {
  await new Promise((resolve) => setTimeout(resolve, 400));
  return {
    command_id: "44444444-4444-4444-8444-444444444444",
    work_item_id: primaryId,
    status: "accepted",
    action_run_id: null,
    accepted_at: new Date().toISOString(),
  };
}
