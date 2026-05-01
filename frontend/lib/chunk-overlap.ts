import type { ChunkItem } from "@/lib/types";

const JOINER = "\n\n";
const MIN_OVERLAP_CHARACTERS = 12;
const MAX_OVERLAP_SCAN_CHARACTERS = 8000;

export interface OverlapAwareChunk {
  chunk: ChunkItem;
  content: string;
  uniqueContent: string;
  overlapContent: string;
  overlapCharacters: number;
}

export interface MergedChunkContent {
  content: string;
  chunks: OverlapAwareChunk[];
  totalOverlapCharacters: number;
  overlappedChunkCount: number;
}

export function mergeChunkContent(chunks: ChunkItem[]): MergedChunkContent {
  const sortedChunks = chunks.slice().sort((left, right) => left.chunk_index - right.chunk_index);
  const overlapAwareChunks: OverlapAwareChunk[] = [];
  let mergedContent = "";
  let totalOverlapCharacters = 0;
  let overlappedChunkCount = 0;

  for (const chunk of sortedChunks) {
    const content = chunk.content.trim();
    const overlapCharacters = mergedContent ? findSuffixPrefixOverlap(mergedContent, content) : 0;
    const overlapContent = content.slice(0, overlapCharacters);
    const uniqueContent = content.slice(overlapCharacters);

    if (content) {
      if (!mergedContent) {
        mergedContent = content;
      } else if (overlapCharacters > 0) {
        mergedContent += uniqueContent;
      } else {
        mergedContent += `${JOINER}${content}`;
      }
    }

    if (overlapCharacters > 0) {
      totalOverlapCharacters += overlapCharacters;
      overlappedChunkCount += 1;
    }

    overlapAwareChunks.push({
      chunk,
      content,
      uniqueContent,
      overlapContent,
      overlapCharacters,
    });
  }

  return {
    content: mergedContent,
    chunks: overlapAwareChunks,
    totalOverlapCharacters,
    overlappedChunkCount,
  };
}

function findSuffixPrefixOverlap(left: string, right: string): number {
  if (!left || !right) return 0;

  const leftTail = left.slice(-MAX_OVERLAP_SCAN_CHARACTERS);
  const rightHead = right.slice(0, MAX_OVERLAP_SCAN_CHARACTERS);
  const maxLength = Math.min(leftTail.length, rightHead.length);

  for (let length = maxLength; length >= MIN_OVERLAP_CHARACTERS; length -= 1) {
    const candidate = rightHead.slice(0, length);
    if (candidate.replace(/\s/g, "").length < MIN_OVERLAP_CHARACTERS) continue;
    if (leftTail.endsWith(candidate)) return length;
  }

  return 0;
}