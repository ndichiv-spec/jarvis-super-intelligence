const SUPPORTED_VERSIONS = new Set(['1.0', '1.1']);
const SUPPORTED_COMPONENTS = new Set([
  'conversation.markdown',
  'research.source_list',
  'workspace.match_list',
  'geospatial.point_map',
]);

export const WEB_RENDERER_CAPABILITIES = Object.freeze({
  contract_versions: ['1.0', '1.1'],
  components: [...SUPPORTED_COMPONENTS],
  modalities: ['text', 'links', 'map'],
});

export function interpretPresentation(
  value,
  rendererCapabilities = WEB_RENDERER_CAPABILITIES,
) {
  if (!value || typeof value !== 'object') return null;
  const fallback = typeof value.fallback?.text === 'string'
    && value.fallback.text.length <= 12000
    ? value.fallback.text
    : null;
  if (!SUPPORTED_VERSIONS.has(value.contract_version)) {
    return fallback === null
      ? null
      : { kind: 'fallback', text: fallback, reason: 'Unsupported contract version.' };
  }
  const version = value.contract_version;
  if (
    value.environment !== 'conversation'
    || !Array.isArray(value.components)
    || !Array.isArray(value.content_hierarchy)
  ) return fallback === null ? null : {
    kind: 'fallback',
    text: fallback,
    reason: 'Invalid presentation contract.',
  };
  const requiredComponents = value.renderer_requirements?.required_components;
  const unsupportedComponents = Array.isArray(requiredComponents)
    ? requiredComponents.filter(
      (type) => !rendererCapabilities.components.includes(type),
    )
    : [];
  if (
    value.renderer_requirements?.contract_version !== version
    || !rendererCapabilities.contract_versions.includes(version)
    || (
      version === '1.1'
      && (
        JSON.stringify(value.renderer_requirements?.supported_contract_versions)
          !== JSON.stringify(['1.0', '1.1'])
        || !Array.isArray(value.renderer_requirements?.required_modalities)
        || value.renderer_requirements.required_modalities.some(
          (modality) => !rendererCapabilities.modalities.includes(modality),
        )
      )
    )
    || !Array.isArray(requiredComponents)
    || requiredComponents.some((type) => !SUPPORTED_COMPONENTS.has(type))
    || unsupportedComponents.length > 0
    || value.components.some((component) => (
      !component
      || typeof component !== 'object'
      || !SUPPORTED_COMPONENTS.has(component.type)
    ))
  ) {
    return fallback === null
      ? null
      : { kind: 'fallback', text: fallback, reason: 'Unsupported presentation component.' };
  }

  if (version === '1.1' && !isValidV11Metadata(value)) {
    return fallback === null ? null : {
      kind: 'fallback',
      text: fallback,
      reason: 'Invalid presentation continuity metadata.',
    };
  }

  const ids = new Set(value.components.map((component) => component.id));
  if (
    !value.content_hierarchy.every((id) => ids.has(id))
    || !ids.has(value.focus)
  ) return fallback === null ? null : { kind: 'fallback', text: fallback, reason: 'Invalid content hierarchy.' };

  if (!Array.isArray(value.data_refs)) return fallback === null ? null : {
    kind: 'fallback',
    text: fallback,
    reason: 'Invalid presentation data references.',
  };
  const references = new Map();
  for (const reference of value.data_refs) {
    if (
      !reference
      || typeof reference.id !== 'string'
      || ![
        'public_source',
        'workspace_result',
        'user_provided_coordinates',
      ].includes(reference.kind)
      || references.has(reference.id)
    ) return fallback === null ? null : {
      kind: 'fallback',
      text: fallback,
      reason: 'Invalid presentation data references.',
    };
    references.set(reference.id, reference.kind);
  }

  function isValidV11Metadata(value) {
    if (
      !value.task_state
      || !['completed', 'partial', 'error', 'unsupported'].includes(value.task_state.status)
      || typeof value.task_state.message !== 'string'
      || !Array.isArray(value.source_provenance)
      || !Array.isArray(value.media_refs)
      || value.media_refs.length !== 0
      || value.user_preferences !== null
      || !value.view_state
      || value.view_state.focus !== value.focus
    ) return false;

    const dataRefs = new Map();
    for (const item of value.data_refs) {
      if (
        !item
        || typeof item.id !== 'string'
        || ![
          'public_source',
          'workspace_result',
          'user_provided_coordinates',
        ].includes(item.kind)
        || dataRefs.has(item.id)
      ) return false;
      dataRefs.set(item.id, item.kind);
    }
    const seen = new Set();
    for (const source of value.source_provenance) {
      if (!source || typeof source !== 'object') return false;
      const expectedKind = source.source_type === 'public_web'
        ? 'public_source'
        : source.source_type === 'authorized_workspace'
          ? 'workspace_result'
          : source.source_type === 'user_provided_coordinates'
            ? 'user_provided_coordinates'
          : null;
      if (
        !expectedKind
        || dataRefs.get(source.data_ref) !== expectedKind
        || seen.has(source.data_ref)
        || typeof source.observed_at !== 'string'
        || Number.isNaN(Date.parse(source.observed_at))
        || !/(Z|[+-]\d{2}:\d{2})$/.test(source.observed_at)
      ) return false;
      seen.add(source.data_ref);
    }
    return seen.size === dataRefs.size
      && (
        value.view_state.selected_data_ref === null
        || dataRefs.has(value.view_state.selected_data_ref)
      );
  }
  const navigationRefs = new Set();
  if (!Array.isArray(value.interactions)) return fallback === null ? null : {
    kind: 'fallback',
    text: fallback,
    reason: 'Invalid presentation interactions.',
  };
  for (const interaction of value.interactions) {
    if (
      !interaction
      || interaction.type !== 'external_source_navigation'
      || typeof interaction.data_ref !== 'string'
      || interaction.required_permissions?.length !== 1
      || interaction.required_permissions[0] !== 'web:read'
      || interaction.user_gesture_required !== true
      || references.get(interaction.data_ref) !== 'public_source'
      || navigationRefs.has(interaction.data_ref)
    ) return fallback === null ? null : {
      kind: 'fallback',
      text: fallback,
      reason: 'Unsupported presentation interaction.',
    };
    navigationRefs.add(interaction.data_ref);
  }
  for (const component of value.components) {
    if (component.type === 'conversation.markdown') {
      if (typeof component.text !== 'string') return null;
      continue;
    }
    if (!Array.isArray(component.items)) return null;
    for (const item of component.items) {
      const expectedKind = component.type === 'research.source_list'
        ? 'public_source'
        : component.type === 'workspace.match_list'
          ? 'workspace_result'
          : 'user_provided_coordinates';
      if (
        typeof item.data_ref !== 'string'
        || references.get(item.data_ref) !== expectedKind
      ) {
        return fallback === null
          ? null
          : { kind: 'fallback', text: fallback, reason: 'Unauthorized data reference.' };
      }
      if (
        component.type === 'research.source_list'
        && (
          !isPublicHttpsUrl(item.url)
          || !navigationRefs.has(item.data_ref)
        )
      ) return fallback === null ? null : {
        kind: 'fallback',
        text: fallback,
        reason: 'Unsupported source reference.',
      };
      if (
        component.type === 'workspace.match_list'
        && (!Number.isInteger(item.line) || item.line < 1 || !isSafeWorkspacePath(item.path))
      ) return fallback === null ? null : {
        kind: 'fallback',
        text: fallback,
        reason: 'Unsupported workspace reference.',
      };
      if (
        component.type === 'geospatial.point_map'
        && (
          typeof item.latitude !== 'number'
          || !Number.isFinite(item.latitude)
          || item.latitude < -90
          || item.latitude > 90
          || typeof item.longitude !== 'number'
          || !Number.isFinite(item.longitude)
          || item.longitude < -180
          || item.longitude > 180
          || item.location_type !== 'user_provided'
          || item.units?.latitude !== 'degrees_north'
          || item.units?.longitude !== 'degrees_east'
        )
      ) return fallback === null ? null : {
        kind: 'fallback',
        text: fallback,
        reason: 'Unsupported map coordinate.',
      };
    }
  }
  return { kind: 'contract', contract: value };
}

function isPublicHttpsUrl(value) {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    return url.protocol === 'https:'
      && !url.username
      && !url.password
      && (url.port === '' || url.port === '443')
      && host !== 'localhost'
      && !host.endsWith('.localhost')
      && !host.endsWith('.local')
      && !host.endsWith('.internal')
      && !/(token|secret|password|credential|auth|session|signature|^key$|^sig$)/i
        .test(url.search);
  } catch {
    return false;
  }
}

function isSafeWorkspacePath(value) {
  return typeof value === 'string'
    && value.length > 0
    && !value.startsWith('/')
    && !/^[A-Za-z]:/.test(value)
    && !value.split(/[\\/]/).some((part) => part === '..' || part === '.')
    && !/[\r\n`<>]/.test(value);
}
