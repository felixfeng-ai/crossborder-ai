/**
 * VeyaShip Mobile Design Tokens
 *
 * 移动端是 DESIGN.md 中「石墨」Web 主题的浅色分支，规则一致：安静、精密、克制。
 * 任何页面样式改动都必须通过这里的 token，不允许在页面里写裸色值。
 *
 * 三条硬约束：
 * 1. 画布永远比卡片暗一档 —— 否则卡片和背景糊成一片，页面失去层级。
 * 2. 一屏只允许一个最大字 —— 卡片主标题与页面标题不得同级。
 * 3. 彩色只给语义，不给装饰 —— 状态色只表达状态，不做品牌装饰和渐变。
 */
export const colors = {
  // 层级：画布 < 卡片。画布用 #F2F3F5，卡片纯白，白卡才会浮起来。
  background: "#F2F3F5",
  surface: "#F7F8FA",
  surfaceQuiet: "#F0F2F5",

  // 卡片
  card: "#FFFFFF",
  cardBorder: "#E9EBEE",

  // 文字三级：主文 / 副文 / 标注
  ink: "#111419",
  inkSoft: "#22262D",
  muted: "#68707C",
  mutedStrong: "#536071",
  faint: "#A0A5AC",

  // 发丝线
  line: "#ECEEF1",

  // 反相主黑：主按钮与决策卡
  black: "#0B0E12",
  blackSoft: "#111315",
  white: "#FFFFFF",

  accent: "#2F6BFF",
  // 蓝色只表达「未读」，其余地方一律不用蓝：
  // 链接、可点文字走 ink + chevron，避免「可点」和「未读」被读成同一件事。
  unread: "#2F6BFF",
  warmWhite: "#F8F7F3",
  danger: "#C63D3D",

  // 语义状态色 —— 底座 + 深色字，保证在浅色底上的对比度
  amber: "#FBE8C8",
  amberInk: "#7A4A0A",
  amberLine: "#F0D8AE",
  // 时间轴上的「现在」标记：黑白底上都要立得住，所以取中间明度。
  amberDot: "#E39A33",
  green: "#3FA872",
  greenSoft: "#E8F5EE",
  greenInk: "#1F6B45",
  // 详情页 / 会话气泡的两组状态底色：只做「危险」与「信息」两档，
  // 不引入第三、第四种色相，避免详情页长出体系外的颜色。
  dangerSoft: "#FFF5F3",
  dangerLine: "#F1D9D4",
  infoSoft: "#EFF4FB",
  infoLine: "#DDE7F4",
  infoInk: "#3A5C86",
  // 时间轴是全 App 唯一允许渐变的地方，这两档只服务于它。
  timelineTrack: "#E1E5EA",
  timelineStart: "#B6BEC7",
  gray: "#8A9099",
  graySoft: "#EFF1F3",
  grayInk: "#55606C",
} as const;

export const fonts = {
  regular: "NotoSansSC",
  medium: "NotoSansSCMedium",
  semibold: "NotoSansSCSemiBold",
  inter: "Inter_400Regular",
  interSemibold: "Inter_600SemiBold",
} as const;

/**
 * 字号只有三档跨度。中文不要超过 semibold —— 再重就会糊。
 */
export const type = {
  cardTitle: 30,
  cardTitleCompact: 26,
  cardTitleDense: 22,
  pageTitle: 22,
  body: 15,
  meta: 13,
  caption: 12,
} as const;

/**
 * 圆角只用三档。混合使用更多档位是「demo 感」的主要来源之一。
 */
export const radii = {
  small: 12,
  medium: 18,
  large: 24,
  hero: 28,
  pill: 999,
} as const;

export const spacing = {
  x1: 4,
  x2: 8,
  x3: 12,
  x4: 16,
  x5: 20,
  x6: 24,
  x7: 28,
  x8: 32,
  x10: 40,
} as const;

/**
 * 只有真实浮起的卡片和浮层允许投影，静止面不投影。
 */
export const shadows = {
  card: {
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 12,
    elevation: 2,
  },
  floating: {
    shadowColor: "#101828",
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.1,
    shadowRadius: 24,
    elevation: 8,
  },
} as const;

/**
 * 主按钮尺寸。按钮高度约为输入框高度的 0.96 倍 —— 两者等高，
 * 一旦按钮超过输入框 1.2 倍，整页立刻失衡。
 */
export const control = {
  buttonHeight: 52,
  fieldHeight: 54,
  radius: 14,
  buttonFontSize: 17,
  fieldFontSize: 15,
} as const;
