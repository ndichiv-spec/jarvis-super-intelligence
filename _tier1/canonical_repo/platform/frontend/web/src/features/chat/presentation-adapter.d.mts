import type { SemanticPresentationContract } from './types';

export type PresentationInterpretation =
  | { kind: 'contract'; contract: SemanticPresentationContract }
  | { kind: 'fallback'; text: string; reason: string };

export function interpretPresentation(
  value: SemanticPresentationContract | undefined,
  rendererCapabilities?: {
    contract_versions: string[];
    components: string[];
    modalities: string[];
  },
): PresentationInterpretation | null;
