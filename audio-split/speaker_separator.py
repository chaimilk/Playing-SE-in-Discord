"""
話者分離プログラム
MP3音声ファイルから2人の話者の音声を自動で分離し、
それぞれ別のMP3ファイルとして出力します。

使い方:
    python speaker_separator.py <入力ファイル> [--num_speakers 2]
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import librosa
import soundfile as sf
from resemblyzer import VoiceEncoder, preprocess_wav
from spectralcluster import SpectralClusterer
from pydub import AudioSegment


def load_audio(input_path: str) -> tuple[np.ndarray, int]:
    """音声ファイルを読み込み、16kHz モノラルの numpy 配列として返す。"""
    print(f"音声ファイルを読み込み中: {input_path}")
    wav, sr = librosa.load(input_path, sr=16000, mono=True)
    print(f"  サンプリングレート: {sr} Hz, 長さ: {len(wav) / sr:.1f} 秒")
    return wav, sr


def create_segments(
    wav: np.ndarray, sr: int, segment_duration: float = 1.5, hop_duration: float = 0.75
) -> list[dict]:
    """音声をオーバーラップするセグメントに分割する。"""
    segment_len = int(segment_duration * sr)
    hop_len = int(hop_duration * sr)
    segments = []
    for start in range(0, len(wav) - segment_len + 1, hop_len):
        end = start + segment_len
        segments.append({
            "start_sample": start,
            "end_sample": end,
            "start_time": start / sr,
            "end_time": end / sr,
            "audio": wav[start:end],
        })
    return segments


def compute_embeddings(segments: list[dict], encoder: VoiceEncoder) -> np.ndarray:
    """各セグメントの話者埋め込みベクトルを計算する。"""
    print(f"話者埋め込みを計算中 ({len(segments)} セグメント)...")
    embeddings = []
    for i, seg in enumerate(segments):
        processed = preprocess_wav(seg["audio"], source_sr=16000)
        if len(processed) < 160:
            embedding = np.zeros(256)
        else:
            embedding = encoder.embed_utterance(processed)
        embeddings.append(embedding)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(segments)} 完了")
    print(f"  全 {len(segments)} セグメントの埋め込み計算完了")
    return np.array(embeddings)


def cluster_speakers(embeddings: np.ndarray, num_speakers: int) -> np.ndarray:
    """話者埋め込みをクラスタリングして話者ラベルを割り当てる。"""
    print(f"話者クラスタリング中 (話者数: {num_speakers})...")
    clusterer = SpectralClusterer(min_clusters=num_speakers, max_clusters=num_speakers)
    labels = clusterer.predict(embeddings)
    unique, counts = np.unique(labels, return_counts=True)
    for label, count in zip(unique, counts):
        print(f"  話者 {label + 1}: {count} セグメント")
    return labels


def build_speaker_masks(
    labels: np.ndarray,
    segments: list[dict],
    total_samples: int,
    num_speakers: int,
) -> list[np.ndarray]:
    """各話者のサンプルレベルのマスク(重み)を構築する。"""
    masks = [np.zeros(total_samples, dtype=np.float32) for _ in range(num_speakers)]
    counts = np.zeros(total_samples, dtype=np.float32)

    for seg, label in zip(segments, labels):
        s = seg["start_sample"]
        e = seg["end_sample"]
        masks[label][s:e] += 1.0
        counts[s:e] += 1.0

    counts = np.maximum(counts, 1e-8)
    for i in range(num_speakers):
        masks[i] /= counts

    return masks


def apply_smoothing(mask: np.ndarray, sr: int, window_ms: int = 100) -> np.ndarray:
    """マスクを滑らかにしてノイズを減らす。"""
    window_size = int(sr * window_ms / 1000)
    if window_size < 1:
        return mask
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(mask, kernel, mode="same")
    return smoothed


def separate_and_export(
    input_path: str,
    wav: np.ndarray,
    sr: int,
    masks: list[np.ndarray],
    output_dir: str,
    base_name: str,
) -> list[str]:
    """マスクを適用して各話者の音声をMP3として書き出す。"""
    output_paths = []
    original_audio = AudioSegment.from_file(input_path)

    for i, mask in enumerate(masks):
        smoothed = apply_smoothing(mask, sr)
        threshold = 0.3
        binary_mask = (smoothed > threshold).astype(np.float32)

        fade_samples = int(sr * 0.02)
        for j in range(1, len(binary_mask)):
            if binary_mask[j] != binary_mask[j - 1]:
                start_fade = max(0, j - fade_samples)
                end_fade = min(len(binary_mask), j + fade_samples)
                fade_region = np.linspace(
                    binary_mask[start_fade], binary_mask[end_fade - 1], end_fade - start_fade
                )
                binary_mask[start_fade:end_fade] = fade_region

        speaker_wav = wav * binary_mask
        temp_wav_path = os.path.join(output_dir, f"temp_speaker_{i + 1}.wav")
        sf.write(temp_wav_path, speaker_wav, sr)

        output_filename = f"{base_name}_speaker{i + 1}.mp3"
        output_path = os.path.join(output_dir, output_filename)

        temp_audio = AudioSegment.from_wav(temp_wav_path)
        temp_audio.export(output_path, format="mp3", bitrate="192k")

        os.remove(temp_wav_path)
        output_paths.append(output_path)

        duration = len(speaker_wav) / sr
        speaking_time = np.sum(binary_mask > 0.5) / sr
        print(f"  話者 {i + 1}: {output_path}")
        print(f"    全体長: {duration:.1f}秒, 発話時間: {speaking_time:.1f}秒")

    return output_paths


def main():
    parser = argparse.ArgumentParser(description="話者分離プログラム")
    parser.add_argument("input_file", help="入力音声ファイル (MP3)")
    parser.add_argument(
        "--num_speakers", type=int, default=2, help="話者数 (デフォルト: 2)"
    )
    parser.add_argument(
        "--output_dir", default=None, help="出力ディレクトリ (デフォルト: 入力ファイルと同じ)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"エラー: ファイルが見つかりません: {args.input_file}")
        sys.exit(1)

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.input_file))
    os.makedirs(output_dir, exist_ok=True)

    base_name = Path(args.input_file).stem

    wav, sr = load_audio(args.input_file)
    segments = create_segments(wav, sr)
    print(f"セグメント数: {len(segments)}")

    encoder = VoiceEncoder()
    embeddings = compute_embeddings(segments, encoder)
    labels = cluster_speakers(embeddings, args.num_speakers)
    masks = build_speaker_masks(labels, segments, len(wav), args.num_speakers)

    print("\n音声ファイルを書き出し中...")
    output_paths = separate_and_export(
        args.input_file, wav, sr, masks, output_dir, base_name
    )

    print(f"\n完了! {len(output_paths)} 個のファイルを出力しました:")
    for path in output_paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
