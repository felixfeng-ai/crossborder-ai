import { Image } from "expo-image";
import { router, type Href } from "expo-router";
import {
  Check,
  ChevronRight,
  Eye,
  EyeOff,
  Lock,
  Mail,
  UserRound,
} from "lucide-react-native";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { ScrollViewInstance, TextStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ApiError,
  checkUsernameAvailability,
  login,
  register,
} from "@/api/client";
import { VeyaShipWordmark } from "@/components/VeyaShipWordmark";
import { signInMark } from "@/design/assets";
import {
  nextPasswordVisibility,
  SIGN_IN_COLORS,
  SIGN_IN_INTERACTION,
  SIGN_IN_LAYOUT,
  SIGN_IN_TYPE,
  validateUsername,
} from "@/design/auth-layout";
import { colors, fonts } from "@/design/tokens";
import {
  LEGAL_CENTER_PATH,
  legalDocumentPath,
  loginConsentCopy,
  registerConsentCopy,
  registerConsentLinks,
  registerConsentTitle,
  type LegalDocumentId,
  validateRegistrationConsent,
} from "@/features/legal/documents";
import { useAuthStore } from "@/stores/auth";

type Mode = "login" | "register";

const webInputStyle =
  Platform.OS === "web"
    ? ({ outlineStyle: "none" } as unknown as TextStyle)
    : undefined;

export default function SignInScreen() {
  const setSession = useAuthStore((state) => state.setSession);
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [usernameError, setUsernameError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [legalAccepted, setLegalAccepted] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<ScrollViewInstance>(null);
  const usernameTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const showEvent =
      Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const hideEvent =
      Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";
    const showSubscription = Keyboard.addListener(showEvent, () => {
      setKeyboardVisible(true);
    });
    const hideSubscription = Keyboard.addListener(hideEvent, () => {
      setKeyboardVisible(false);
      scrollRef.current?.scrollTo({ y: 0, animated: true });
    });

    return () => {
      showSubscription.remove();
      hideSubscription.remove();
    };
  }, []);

  useEffect(() => {
    if (!keyboardVisible) return;

    // 键盘出现后把底部主操作滚入可视区，避免输入时按钮被键盘遮挡。
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [keyboardVisible]);

  useEffect(
    () => () => {
      if (usernameTimerRef.current) {
        clearTimeout(usernameTimerRef.current);
      }
    },
    [],
  );

  const inspectUsername = async (value: string) => {
    if (validateUsername(value)) {
      setUsernameError("请输入 4–12 位中文、字母、数字或下划线");
      return false;
    }

    try {
      const result = await checkUsernameAvailability(value);
      if (!result.available) {
        setUsernameError("这个称呼已经被用了");
        return false;
      }
      setUsernameError("");
      return true;
    } catch (reason) {
      setUsernameError(
        reason instanceof ApiError
          ? reason.message
          : "暂时无法检查称呼，请稍后重试",
      );
      return false;
    }
  };

  const queueUsernameCheck = () => {
    if (usernameTimerRef.current) {
      clearTimeout(usernameTimerRef.current);
    }
    if (!username) {
      setUsernameError("请输入 4–12 位中文、字母、数字或下划线");
      return;
    }
    if (validateUsername(username)) {
      setUsernameError("请输入 4–12 位中文、字母、数字或下划线");
      return;
    }

    usernameTimerRef.current = setTimeout(() => {
      void inspectUsername(username);
    }, SIGN_IN_INTERACTION.usernameDebounceMs);
  };

  const submit = async () => {
    if (pending) return;

    if (mode === "register") {
      const consentError = validateRegistrationConsent(legalAccepted);
      if (consentError) {
        setError(consentError);
        return;
      }
      const normalizedUsername = username.trim();
      if (validateUsername(normalizedUsername)) {
        setUsernameError("请输入 4–12 位中文、字母、数字或下划线");
        return;
      }
      const available = await inspectUsername(normalizedUsername);
      if (!available) return;
    } else if (!email.trim() || !password.trim()) {
      setError("请输入邮箱和密码");
      return;
    }

    if (!email.trim() || !password.trim()) {
      setError("请输入邮箱和密码");
      return;
    }

    setPending(true);
    setError("");

    try {
      const result =
        mode === "login"
          ? await login(email.trim(), password)
          : await register(
              email.trim(),
              username.trim(),
              password,
            );
      await setSession(result);
      router.replace("/");
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "无法连接服务，请检查网络后重试",
      );
    } finally {
      setPending(false);
    }
  };

  const openLegalPage = (documentId: LegalDocumentId) => {
    router.push(legalDocumentPath(documentId) as Href);
  };

  return (
    <SafeAreaView edges={["left", "right"]} style={styles.safe}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.flex}
      >
        <ScrollView
          bounces={mode === "register"}
          contentContainerStyle={styles.scrollContent}
          keyboardDismissMode={Platform.OS === "ios" ? "interactive" : "on-drag"}
          keyboardShouldPersistTaps="handled"
          ref={scrollRef}
          scrollEnabled={mode === "register" || keyboardVisible}
          showsVerticalScrollIndicator={false}
          style={styles.flex}
        >
          <View style={styles.content}>
            <Image
              accessibilityLabel="VeyaShip Logo"
              contentFit="contain"
              source={signInMark}
              style={styles.logo}
            />

            <View style={styles.wordmark}>
              <VeyaShipWordmark width={160} />
            </View>

            <Text style={styles.tagline}>
              一台手机，一个 Agent，一天的跨境工作
            </Text>

            <View style={styles.fields}>
              {mode === "register" && (
                <View style={styles.usernameGroup}>
                  <View style={[styles.field, styles.signupField]}>
                    <UserRound
                      color={SIGN_IN_COLORS.placeholder}
                      size={SIGN_IN_LAYOUT.fieldIconSize}
                      strokeWidth={1.7}
                    />
                    <TextInput
                      accessibilityLabel="用户名"
                      autoCapitalize="none"
                      autoComplete="username"
                      autoCorrect={false}
                      maxLength={12}
                      onBlur={queueUsernameCheck}
                      onChangeText={(value) => {
                        setUsername(value);
                        setUsernameError("");
                        if (usernameTimerRef.current) {
                          clearTimeout(usernameTimerRef.current);
                        }
                      }}
                      placeholder="小Veya 怎么称呼你"
                      placeholderTextColor={SIGN_IN_COLORS.placeholder}
                      returnKeyType="next"
                      style={[
                        styles.input,
                        webInputStyle,
                      ]}
                      value={username}
                    />
                  </View>
                  {!!usernameError && (
                    <Text
                      accessibilityLiveRegion="polite"
                      style={styles.usernameError}
                    >
                      {usernameError}
                    </Text>
                  )}
                </View>
              )}

              <View style={[styles.field, mode === "register" && styles.signupField]}>
                <Mail
                  color={SIGN_IN_COLORS.placeholder}
                  size={SIGN_IN_LAYOUT.fieldIconSize}
                  strokeWidth={1.7}
                />
                <TextInput
                  accessibilityLabel="邮箱"
                  autoCapitalize="none"
                  autoComplete="email"
                  autoCorrect={false}
                  keyboardType="email-address"
                  onChangeText={(value) => {
                    setEmail(value);
                    if (error) setError("");
                  }}
                  placeholder="name@company.com"
                  placeholderTextColor={SIGN_IN_COLORS.placeholder}
                  returnKeyType="next"
                  style={[
                    styles.input,
                    webInputStyle,
                  ]}
                  value={email}
                />
              </View>

              <View
                style={[
                  styles.field,
                  mode === "register" && styles.signupField,
                  styles.passwordField,
                ]}
              >
                <Lock
                  color={SIGN_IN_COLORS.placeholder}
                  size={SIGN_IN_LAYOUT.fieldIconSize}
                  strokeWidth={1.7}
                />
                <TextInput
                  accessibilityLabel="密码"
                  autoCapitalize="none"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  autoCorrect={false}
                  onChangeText={(value) => {
                    setPassword(value);
                    if (error) setError("");
                  }}
                  onSubmitEditing={() => void submit()}
                  placeholder="输入密码"
                  placeholderTextColor={SIGN_IN_COLORS.placeholder}
                  returnKeyType="go"
                  secureTextEntry={!passwordVisible}
                  style={[
                    styles.input,
                    webInputStyle,
                  ]}
                  value={password}
                />
                <Pressable
                  accessibilityLabel={
                    passwordVisible ? "隐藏密码" : "显示密码"
                  }
                  accessibilityRole="button"
                  hitSlop={4}
                  onPress={() => setPasswordVisible(nextPasswordVisibility)}
                  style={({ pressed }) => [
                    styles.eyeButton,
                    pressed && styles.eyeButtonPressed,
                  ]}
                >
                  {passwordVisible ? (
                    <EyeOff
                      color={SIGN_IN_COLORS.placeholder}
                      size={18}
                      strokeWidth={1.7}
                    />
                  ) : (
                    <Eye
                      color={SIGN_IN_COLORS.placeholder}
                      size={18}
                      strokeWidth={1.7}
                    />
                  )}
                </Pressable>
              </View>
            </View>

            {mode === "register" && (
              <Pressable
                accessibilityRole="checkbox"
                accessibilityLabel={registerConsentCopy}
                accessibilityState={{ checked: legalAccepted }}
                onPress={() => {
                  setLegalAccepted((current) => !current);
                  if (error) setError("");
                }}
                style={({ pressed }) => [
                  styles.consentRow,
                  pressed && styles.consentRowPressed,
                ]}
              >
                <View
                  style={[
                    styles.checkbox,
                    legalAccepted && styles.checkboxChecked,
                  ]}
                >
                  {legalAccepted && (
                    <Check
                      color={SIGN_IN_COLORS.white}
                      size={13}
                      strokeWidth={2.4}
                    />
                  )}
                </View>
                <View style={styles.consentCopy}>
                  <Text style={styles.consentTitle}>
                    {registerConsentTitle}
                  </Text>
                  <Text style={styles.consentLinks}>
                    {registerConsentLinks}
                  </Text>
                </View>
              </Pressable>
            )}

            <Pressable
              accessibilityLabel={
                pending
                  ? mode === "register"
                    ? "正在创建账号"
                    : "正在登录"
                  : mode === "register"
                    ? "创建账号"
                    : "进入工作台"
              }
              accessibilityRole="button"
              disabled={pending}
              onPress={() => void submit()}
              style={({ pressed }) => [
                styles.button,
                pressed && !pending && styles.buttonPressed,
              ]}
            >
              {pending ? (
                <View style={styles.loadingSlot}>
                  <ActivityIndicator color={SIGN_IN_COLORS.white} />
                </View>
              ) : (
                <Text style={styles.buttonText}>
                  {mode === "register" ? "创建账号" : "进入工作台"}
                </Text>
              )}
            </Pressable>

            {error ? (
              <Text accessibilityLiveRegion="polite" style={styles.legalError}>
                {error}
              </Text>
            ) : null}

            {mode === "login" && (
              <View
                accessibilityLabel={loginConsentCopy}
                style={styles.legalRow}
              >
                <Text style={styles.legalText}>登录即代表同意</Text>
                <Pressable
                  accessibilityRole="link"
                  hitSlop={{ top: 13, bottom: 13, left: 2, right: 2 }}
                  onPress={() => openLegalPage("terms")}
                >
                  <Text style={styles.legalLink}>《服务条款》</Text>
                </Pressable>
                <Text style={styles.legalText}>、</Text>
                <Pressable
                  accessibilityRole="link"
                  hitSlop={{ top: 13, bottom: 13, left: 2, right: 2 }}
                  onPress={() => openLegalPage("privacy")}
                >
                  <Text style={styles.legalLink}>《隐私政策》</Text>
                </Pressable>
                <Text style={styles.legalText}>与</Text>
                <Pressable
                  accessibilityRole="link"
                  hitSlop={{ top: 13, bottom: 13, left: 2, right: 2 }}
                  onPress={() => openLegalPage("ai-disclosure")}
                >
                  <Text style={styles.legalLink}>《AI 使用说明》</Text>
                </Pressable>
              </View>
            )}

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="查看全部法律与隐私说明"
              onPress={() => router.push(LEGAL_CENTER_PATH as Href)}
              style={({ pressed }) => [
                styles.allLegalButton,
                pressed && styles.allLegalButtonPressed,
              ]}
            >
              <Text style={styles.allLegalText}>全部法律与隐私</Text>
              <ChevronRight
                color={SIGN_IN_COLORS.secondary}
                size={13}
                strokeWidth={1.9}
              />
            </Pressable>

            <Pressable
              accessibilityHint={
                mode === "login" ? "切换到创建账号" : "切换回登录"
              }
              accessibilityRole="button"
              onPress={() => {
                setMode((current) =>
                  current === "login" ? "register" : "login",
                );
                setError("");
                setUsernameError("");
                setLegalAccepted(false);
                if (usernameTimerRef.current) {
                  clearTimeout(usernameTimerRef.current);
                }
              }}
              style={styles.createAccount}
            >
              <Text style={styles.createAccountMuted}>
                {mode === "login" ? "还没有账号？" : "已有账号？"}
              </Text>
              <Text style={styles.createAccountAction}>
                {mode === "login" ? "创建账号" : "登录"}
              </Text>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: SIGN_IN_COLORS.background,
  },
  flex: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingTop: SIGN_IN_LAYOUT.logoTop,
    paddingBottom: 32,
  },
  content: {
    width: SIGN_IN_LAYOUT.contentWidth,
    alignSelf: "center",
  },
  logo: {
    width: SIGN_IN_LAYOUT.logoSize,
    height: SIGN_IN_LAYOUT.logoSize,
    alignSelf: "center",
  },
  wordmark: {
    marginTop: SIGN_IN_LAYOUT.logoToWordmark,
    alignItems: "center",
  },
  tagline: {
    marginTop: SIGN_IN_LAYOUT.wordmarkToTagline,
    color: SIGN_IN_COLORS.secondary,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.tagline,
    fontWeight: "500",
    letterSpacing: 0.2,
    lineHeight: 20,
    textAlign: "center",
  },
  fields: {
    marginTop: SIGN_IN_LAYOUT.taglineToFields,
    gap: SIGN_IN_LAYOUT.fieldGap,
  },
  usernameGroup: {
    gap: 4,
  },
  field: {
    height: SIGN_IN_LAYOUT.fieldHeight,
    flexDirection: "row",
    alignItems: "center",
    paddingLeft: SIGN_IN_LAYOUT.fieldHorizontalPadding,
    borderWidth: 1,
    borderColor: SIGN_IN_COLORS.border,
    borderRadius: SIGN_IN_LAYOUT.fieldRadius,
    backgroundColor: SIGN_IN_COLORS.white,
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  signupField: {
    height: 58,
  },
  passwordField: {
    paddingRight: 4,
  },
  usernameError: {
    color: colors.danger,
    fontFamily: fonts.regular,
    fontSize: 12,
    lineHeight: 16,
  },
  input: {
    height: "100%",
    flex: 1,
    marginLeft: 12,
    paddingVertical: 0,
    color: SIGN_IN_COLORS.ink,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.input,
    fontWeight: "400",
  },
  eyeButton: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
  },
  eyeButtonPressed: {
    backgroundColor: colors.surface,
  },
  button: {
    width: SIGN_IN_LAYOUT.contentWidth,
    height: SIGN_IN_LAYOUT.buttonHeight,
    alignItems: "center",
    justifyContent: "center",
    marginTop: SIGN_IN_LAYOUT.fieldsToButton,
    overflow: "hidden",
    borderRadius: SIGN_IN_LAYOUT.controlRadius,
    backgroundColor: SIGN_IN_COLORS.button,
  },
  buttonPressed: {
    opacity: SIGN_IN_INTERACTION.pressedOpacity,
  },
  buttonText: {
    color: SIGN_IN_COLORS.white,
    fontFamily: fonts.semibold,
    fontSize: SIGN_IN_TYPE.button,
    fontWeight: "600",
    lineHeight: 22,
  },
  loadingSlot: {
    width: 56,
    height: SIGN_IN_LAYOUT.buttonHeight,
    alignItems: "center",
    justifyContent: "center",
  },
  consentRow: {
    minHeight: 44,
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  consentRowPressed: {
    opacity: 0.62,
  },
  checkbox: {
    width: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: SIGN_IN_COLORS.border,
    borderRadius: 6,
    backgroundColor: SIGN_IN_COLORS.white,
  },
  checkboxChecked: {
    borderColor: SIGN_IN_COLORS.button,
    backgroundColor: SIGN_IN_COLORS.button,
  },
  consentCopy: {
    flex: 1,
    gap: 1,
  },
  consentTitle: {
    color: SIGN_IN_COLORS.secondary,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.legal,
    lineHeight: 18,
  },
  consentLinks: {
    color: SIGN_IN_COLORS.placeholder,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.legal,
    lineHeight: 18,
  },
  legalRow: {
    minHeight: 18,
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "center",
    marginTop: SIGN_IN_LAYOUT.buttonToLegal,
    rowGap: 2,
  },
  legalText: {
    color: SIGN_IN_COLORS.secondary,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.legal,
    fontWeight: "400",
    lineHeight: 18,
  },
  legalLink: {
    color: SIGN_IN_COLORS.secondary,
    fontFamily: fonts.medium,
    fontSize: SIGN_IN_TYPE.legal,
    fontWeight: "500",
    lineHeight: 18,
  },
  legalError: {
    minHeight: 18,
    marginTop: SIGN_IN_LAYOUT.buttonToLegal,
    color: colors.danger,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.legal,
    lineHeight: 18,
    textAlign: "center",
  },
  allLegalButton: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
  allLegalButtonPressed: {
    opacity: 0.55,
  },
  allLegalText: {
    color: SIGN_IN_COLORS.secondary,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.legal,
    lineHeight: 18,
  },
  createAccount: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: SIGN_IN_LAYOUT.legalToCreateAccount,
    gap: 5,
  },
  createAccountMuted: {
    color: SIGN_IN_COLORS.createAccountMuted,
    fontFamily: fonts.regular,
    fontSize: SIGN_IN_TYPE.createAccount,
    fontWeight: "400",
    lineHeight: 20,
  },
  createAccountAction: {
    color: SIGN_IN_COLORS.ink,
    fontFamily: fonts.semibold,
    fontSize: SIGN_IN_TYPE.createAccount,
    fontWeight: "600",
    lineHeight: 20,
  },
});
