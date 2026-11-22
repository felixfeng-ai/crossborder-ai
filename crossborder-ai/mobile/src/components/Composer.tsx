import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import {
  ImagePickerAsset,
  launchCameraAsync,
  launchImageLibraryAsync,
  requestCameraPermissionsAsync,
} from "expo-image-picker";
import {
  AudioLines,
  Camera,
  ImagePlus,
  Keyboard,
  Link2,
  Plus,
  ScanLine,
} from "lucide-react-native";
import { useEffect, useRef, useState } from "react";
import type { ElementRef } from "react";
import {
  Alert,
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, fonts } from "@/design/tokens";

export type AudioRecordingAsset = {
  uri: string;
  name: string;
  type: string;
  durationMs: number;
  file?: unknown;
};

type Props = {
  sending?: boolean;
  voiceProcessing?: boolean;
  onSendText: (text: string) => Promise<void> | void;
  onPickedImage?: (asset: ImagePickerAsset) => void;
  onRecorded?: (asset: AudioRecordingAsset) => Promise<void> | void;
  draft?: { id: number; text: string } | null;
  onDraftApplied?: (id: number) => void;
};

function audioFileDescriptor(uri: string) {
  const clean = uri.split("?", 1)[0];
  const extension = clean.split(".").pop()?.toLowerCase();
  if (extension === "wav") {
    return { name: `voice-${Date.now()}.wav`, type: "audio/wav" };
  }
  if (extension === "webm") {
    return { name: `voice-${Date.now()}.webm`, type: "audio/webm" };
  }
  if (extension === "ogg") {
    return { name: `voice-${Date.now()}.ogg`, type: "audio/ogg" };
  }
  if (extension === "mp3") {
    return { name: `voice-${Date.now()}.mp3`, type: "audio/mpeg" };
  }
  return { name: `voice-${Date.now()}.m4a`, type: "audio/mp4" };
}

export function Composer({
  sending,
  voiceProcessing,
  onSendText,
  onPickedImage,
  onRecorded,
  draft,
  onDraftApplied,
}: Props) {
  const [value, setValue] = useState("");
  const [recording, setRecording] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [mediaOpen, setMediaOpen] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [inputMode, setInputMode] = useState<"default" | "link" | "order">(
    "default",
  );
  const started = useRef(false);
  const inputRef = useRef<ElementRef<typeof TextInput>>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 250);

  useEffect(() => {
    if (!draft?.text) return;
    const timer = setTimeout(() => {
      setValue(draft.text);
      setInputMode("default");
      inputRef.current?.focus();
      onDraftApplied?.(draft.id);
    }, 220);
    return () => clearTimeout(timer);
  }, [draft, onDraftApplied]);

  const submit = async () => {
    const text = value.trim();
    if (!text || sending) return;
    setValue("");
    setInputMode("default");
    await onSendText(text);
  };

  const pickImage = async () => {
    setMediaOpen(false);
    const result = await launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: false,
      quality: 0.85,
      selectionLimit: 1,
    });
    if (!result.canceled && result.assets[0]) {
      onPickedImage?.(result.assets[0]);
    }
  };

  const takePhoto = async () => {
    const permission = await requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法打开相机", "请在系统设置中允许相机权限。");
      return;
    }
    setMediaOpen(false);
    const result = await launchCameraAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) {
      onPickedImage?.(result.assets[0]);
    }
  };

  const useLinkInput = () => {
    setMoreOpen(false);
    setInputMode("link");
    setTimeout(() => inputRef.current?.focus(), 220);
  };

  const useOrderInput = () => {
    setMoreOpen(false);
    setInputMode("order");
    setTimeout(() => inputRef.current?.focus(), 220);
  };

  const startRecording = async () => {
    if (recording) return;
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("无法录音", "请在系统设置中允许麦克风权限。");
      return;
    }
    await setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
    });
    await recorder.prepareToRecordAsync();
    recorder.record({ forDuration: 60 });
    started.current = true;
    setRecording(true);
  };

  const finishRecording = async () => {
    if (!started.current) return;
    started.current = false;
    const durationMs = Math.max(
      500,
      Math.round(recorderState.durationMillis),
    );
    setRecording(false);
    await recorder.stop();
    await setAudioModeAsync({ allowsRecording: false });
    const uri = recorder.uri;
    if (!uri) return;
    const descriptor = audioFileDescriptor(uri);
    try {
      if (onRecorded) {
        await onRecorded({
          uri,
          durationMs,
          ...descriptor,
        });
      } else {
        Alert.alert(
          "语音已录制",
          "当前页面还未开通语音转写。",
        );
      }
    } catch {
      Alert.alert(
        "语音识别失败",
        "网络恢复后可以重新录制，不会重复创建任务。",
      );
    }
  };

  const placeholder = voiceProcessing
    ? "正在识别语音"
    : recording
    ? `正在录音 ${Math.ceil(recorderState.durationMillis / 1000)} 秒`
    : inputMode === "link"
      ? "粘贴商品或订单链接"
      : inputMode === "order"
        ? "输入订单号或物流单号"
        : "告诉小 Veya 要做什么";

  return (
    <View style={styles.outer}>
      <View style={styles.composer}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="拍照或添加图片"
          onPress={() => setMediaOpen(true)}
          style={({ pressed }) => [
            styles.iconButton,
            pressed && styles.pressed,
          ]}
        >
          <Camera color={colors.inkSoft} size={22} strokeWidth={1.7} />
        </Pressable>
        {voiceMode ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="按住说话"
            onLongPress={startRecording}
            onPressOut={finishRecording}
            disabled={sending}
            delayLongPress={180}
            style={({ pressed }) => [
              styles.voiceHold,
              recording && styles.voiceHoldActive,
              voiceProcessing && styles.voiceHoldProcessing,
              pressed && styles.voiceHoldPressed,
            ]}
          >
            {voiceProcessing ? (
              <ActivityIndicator color={colors.mutedStrong} size="small" />
            ) : (
              <AudioLines
                color={recording ? colors.white : colors.mutedStrong}
                size={18}
                strokeWidth={1.8}
              />
            )}
            <Text
              style={[
                styles.voiceHoldText,
                recording && styles.voiceHoldTextActive,
              ]}
            >
              {voiceProcessing
                ? "正在识别语音"
                : recording
                  ? "松开结束"
                  : "按住 说话"}
            </Text>
          </Pressable>
        ) : (
          <TextInput
            ref={inputRef}
            accessibilityLabel="给 Veya 发消息"
            value={value}
            onChangeText={setValue}
            onSubmitEditing={submit}
            editable={!recording && !voiceProcessing}
            placeholder={placeholder}
            placeholderTextColor={colors.muted}
            returnKeyType="send"
            style={styles.input}
          />
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={voiceMode ? "切换到文字输入" : "语音输入"}
          onPress={() => {
            setVoiceMode((current) => !current);
            setInputMode("default");
          }}
          disabled={sending || recording}
          style={({ pressed }) => [
            styles.voiceIconButton,
            pressed && styles.pressed,
          ]}
        >
          {voiceMode ? (
            <Keyboard color={colors.inkSoft} size={20} strokeWidth={1.8} />
          ) : (
            <AudioLines color={colors.inkSoft} size={21} strokeWidth={1.8} />
          )}
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="更多输入方式"
          onPress={() => setMoreOpen(true)}
          style={({ pressed }) => [
            styles.moreButton,
            pressed && styles.pressed,
          ]}
        >
          <Plus color={colors.white} size={20} strokeWidth={1.8} />
        </Pressable>
      </View>
      <Modal
        transparent
        visible={mediaOpen}
        animationType="fade"
        onRequestClose={() => setMediaOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setMediaOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>添加商品或单据图片</Text>
          <Pressable
            accessibilityRole="button"
            onPress={takePhoto}
            style={({ pressed }) => [
              styles.actionRow,
              pressed && styles.actionPressed,
            ]}
          >
            <Camera color={colors.ink} size={21} strokeWidth={1.7} />
            <Text style={styles.actionLabel}>拍照或扫描单据</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={pickImage}
            style={({ pressed }) => [
              styles.actionRow,
              pressed && styles.actionPressed,
            ]}
          >
            <ImagePlus color={colors.ink} size={21} strokeWidth={1.7} />
            <Text style={styles.actionLabel}>从相册选择</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setMediaOpen(false)}
            style={styles.cancel}
          >
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </SafeAreaView>
      </Modal>

      <Modal
        transparent
        visible={moreOpen}
        animationType="fade"
        onRequestClose={() => setMoreOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setMoreOpen(false)}
        />
        <SafeAreaView style={styles.sheet} edges={["bottom"]}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>添加链接或订单信息</Text>
          <Pressable
            accessibilityRole="button"
            onPress={useLinkInput}
            style={({ pressed }) => [
              styles.actionRow,
              pressed && styles.actionPressed,
            ]}
          >
            <Link2 color={colors.ink} size={21} strokeWidth={1.7} />
            <Text style={styles.actionLabel}>粘贴商品或订单链接</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={useOrderInput}
            style={({ pressed }) => [
              styles.actionRow,
              pressed && styles.actionPressed,
            ]}
          >
            <ScanLine color={colors.ink} size={21} strokeWidth={1.7} />
            <Text style={styles.actionLabel}>输入订单号或物流单号</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setMoreOpen(false)}
            style={styles.cancel}
          >
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </SafeAreaView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    paddingHorizontal: 16,
    paddingTop: 6,
    backgroundColor: colors.background,
  },
  composer: {
    minHeight: 58,
    paddingVertical: 6,
    paddingHorizontal: 7,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderRadius: 29,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.07,
    shadowRadius: 16,
    elevation: 3,
  },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
  },
  moreButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.black,
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.96 }],
  },
  input: {
    flex: 1,
    minWidth: 0,
    paddingHorizontal: 4,
    paddingVertical: 10,
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 13.5,
  },
  voiceIconButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
  },
  voiceHold: {
    minHeight: 42,
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderRadius: 21,
    backgroundColor: colors.surface,
  },
  voiceHoldActive: {
    backgroundColor: colors.ink,
  },
  voiceHoldProcessing: {
    backgroundColor: colors.surfaceQuiet,
  },
  voiceHoldPressed: {
    opacity: 0.72,
  },
  voiceHoldText: {
    color: colors.mutedStrong,
    fontFamily: fonts.medium,
    fontSize: 13,
  },
  voiceHoldTextActive: {
    color: colors.white,
    fontFamily: fonts.semibold,
  },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(10, 13, 18, 0.2)",
  },
  sheet: {
    paddingHorizontal: 22,
    paddingTop: 10,
    paddingBottom: 8,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.white,
  },
  sheetHandle: {
    width: 38,
    height: 4,
    alignSelf: "center",
    borderRadius: 2,
    backgroundColor: colors.line,
  },
  sheetTitle: {
    marginTop: 20,
    marginBottom: 8,
    color: colors.ink,
    fontFamily: fonts.semibold,
    fontSize: 18,
  },
  actionRow: {
    minHeight: 56,
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
  },
  actionPressed: {
    opacity: 0.55,
  },
  actionLabel: {
    color: colors.ink,
    fontFamily: fonts.medium,
    fontSize: 14,
  },
  cancel: {
    minHeight: 48,
    marginTop: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  cancelText: {
    color: colors.muted,
    fontFamily: fonts.medium,
    fontSize: 13,
  },
});
