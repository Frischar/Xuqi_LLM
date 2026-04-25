from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_EMBEDDING_FIELDS = ["title", "content", "tags", "notes"]
DEFAULT_SPRITE_BASE_PATH = "/static/sprites"


class ChatRequest(BaseModel):
    message: str
    runtime_config: dict[str, Any] | None = None


class PersonaPayload(BaseModel):
    name: str
    system_prompt: str
    greeting: str


class SettingsPayload(BaseModel):
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    theme: str = "light"
    temperature: float = 0.85
    history_limit: int = 20
    request_timeout: int = 120
    demo_mode: bool = False
    ui_opacity: float = 0.84
    background_image_url: str = ""
    background_overlay: float = 0.42
    sprite_enabled: bool = True
    sprite_base_path: str = DEFAULT_SPRITE_BASE_PATH
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_fields: list[str] = Field(default_factory=lambda: list(DEFAULT_EMBEDDING_FIELDS))
    retrieval_top_k: int = 4
    rerank_enabled: bool = False
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""
    rerank_top_n: int = 3


class MemoryItemPayload(BaseModel):
    id: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class MemoryListPayload(BaseModel):
    items: list[MemoryItemPayload] = Field(default_factory=list)


class MergedMemoryItemPayload(BaseModel):
    id: str = ""
    title: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    source_memory_ids: list[str] = Field(default_factory=list)
    created_at: str = ""


class MergedMemoryListPayload(BaseModel):
    items: list[MergedMemoryItemPayload] = Field(default_factory=list)


class MemoryOutlineItemPayload(BaseModel):
    id: str = ""
    title: str = ""
    summary: str = ""
    characters: str = ""
    relationship_progress: str = ""
    key_events: list[str] = Field(default_factory=list)
    conflicts: str = ""
    next_hooks: str = ""
    notes: str = ""
    source_memory_ids: list[str] = Field(default_factory=list)
    merged_memory_id: str = ""
    updated_at: str = ""


class MemoryOutlineListPayload(BaseModel):
    items: list[MemoryOutlineItemPayload] = Field(default_factory=list)


class MemoryMergePayload(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)
    merged_title: str = ""
    outline_title: str = ""
    delete_sources: bool = True
    runtime_config: dict[str, Any] | None = None


class UserProfilePayload(BaseModel):
    display_name: str = ""
    nickname: str = ""
    profile_text: str = ""
    notes: str = ""


class WorldbookEntryPayload(BaseModel):
    id: str = ""
    title: str = ""
    trigger: str = ""
    secondary_trigger: str = ""
    content: str = ""
    enabled: bool = True

    # 旧字段兼容
    priority: int = 100

    case_sensitive: bool = False
    whole_word: bool = False
    match_mode: str = "any"
    secondary_mode: str = "all"
    comment: str = ""

    # 新版世界书字段
    group: str = ""
    entry_type: str = "keyword"
    group_operator: str = "and"
    chance: int = 100
    sticky_turns: int = 0
    cooldown_turns: int = 0
    order: int = 100

    # 节点版世界书注入控制
    insertion_position: str = "after_char_defs"
    injection_depth: int = 0
    injection_role: str = "system"
    injection_order: int = 100

    # 递归 V1
    recursive_enabled: bool = True
    prevent_further_recursion: bool = False


class WorldbookSettingsPayload(BaseModel):
    enabled: bool = True
    debug_enabled: bool = False
    max_hits: int = 3
    default_case_sensitive: bool = False
    default_whole_word: bool = False
    default_match_mode: str = "any"
    default_secondary_mode: str = "all"

    # 新版世界书默认字段
    default_entry_type: str = "keyword"
    default_group_operator: str = "and"
    default_chance: int = 100
    default_sticky_turns: int = 0
    default_cooldown_turns: int = 0

    # 节点版世界书注入默认值
    default_insertion_position: str = "after_char_defs"
    default_injection_depth: int = 0
    default_injection_role: str = "system"
    default_injection_order: int = 100

    # 递归 V1
    recursive_scan_enabled: bool = False
    recursion_max_depth: int = 2


class WorldbookPayload(BaseModel):
    items: list[WorldbookEntryPayload] = Field(default_factory=list)
    settings: WorldbookSettingsPayload | None = None


class PresetPromptPayload(BaseModel):
    id: str = ""
    name: str = ""
    enabled: bool = True
    content: str = ""
    order: int = 100


class PresetPromptGroupItemPayload(BaseModel):
    id: str = ""
    name: str = ""
    enabled: bool = True
    content: str = ""


class PresetPromptGroupPayload(BaseModel):
    id: str = ""
    name: str = ""
    enabled: bool = True
    selection_mode: str = "single"
    selected_ids: list[str] = Field(default_factory=list)
    items: list[PresetPromptGroupItemPayload] = Field(default_factory=list)
    order: int = 100


class PresetItemPayload(BaseModel):
    id: str = ""
    name: str = "Preset"
    enabled: bool = True
    base_system_prompt: str = ""
    modules: dict[str, bool] = Field(default_factory=dict)
    extra_prompts: list[PresetPromptPayload] = Field(default_factory=list)
    prompt_groups: list[PresetPromptGroupPayload] = Field(default_factory=list)


class PresetStorePayload(BaseModel):
    active_preset_id: str = ""
    presets: list[PresetItemPayload] = Field(default_factory=list)


class PresetCreatePayload(BaseModel):
    name: str = ""


class PresetActionPayload(BaseModel):
    preset_id: str = ""


class PresetImportPayload(BaseModel):
    raw_json: str = ""
    activate_now: bool = True


class SaveSlotSelectPayload(BaseModel):
    slot_id: str


class SaveSlotRenamePayload(BaseModel):
    slot_id: str
    name: str = ""


class SaveSlotResetPayload(BaseModel):
    slot_id: str


class SpriteDeletePayload(BaseModel):
    filename: str


class RoleCardPayload(BaseModel):
    raw_json: str
    filename: str = ""
    apply_now: bool = True


class RoleCardLoadPayload(BaseModel):
    filename: str


class JsonImportPayload(BaseModel):
    raw_json: str = ""
    apply_settings: bool = True
    missing_injection_policy: str = "follow_defaults"
    force_in_chat_depth: int = 0
    force_injection_order: int | None = None


class WorkshopEvaluatePayload(BaseModel):
    reason: str = "sync"
    advance_temp: bool = False


class WorkshopSavePayload(BaseModel):
    creativeWorkshop: dict[str, Any]


class SlotMetadata(BaseModel):
    slot_id: str = ""
    slot_name: str = ""
    created_at: str = ""
    last_updated: str = ""
    card_id: str = ""


class SlotChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "user"
    content: str = ""
    timestamp: str = ""


class SlotSummaryBuffer(BaseModel):
    content: str = ""
    updated_at: str = ""
    source_message_count: int = 0


class SlotActivePreset(BaseModel):
    preset_id: str = ""
    name: str = ""
    enabled: bool = False
    generation_params: dict[str, Any] = Field(default_factory=dict)
    system_prompt_filter: str = ""
    prompt_fragments: list[str] = Field(default_factory=list)
    modules: dict[str, bool] = Field(default_factory=dict)


class SlotVariableStore(BaseModel):
    model_config = ConfigDict(extra="allow")

    favorability: float = 0.0
    current_stage: str = "A"
    virtual_time: str = ""


class SlotRuntimeMedia(BaseModel):
    background_image_url: str = ""
    background_overlay: float = 0.42
    bgm_url: str = ""
    bgm_preset: str = ""
    media_note: str = ""


class SlotEnvironmentState(BaseModel):
    active_preset: SlotActivePreset = Field(default_factory=SlotActivePreset)
    variable_store: SlotVariableStore = Field(default_factory=SlotVariableStore)
    runtime_media: SlotRuntimeMedia = Field(default_factory=SlotRuntimeMedia)


class SlotWorldbookContext(BaseModel):
    unlocked_entry_ids: list[str] = Field(default_factory=list)
    active_entry_ids: list[str] = Field(default_factory=list)
    last_trigger_terms: list[str] = Field(default_factory=list)
    last_injected_at: str = ""


class SlotState(BaseModel):
    metadata: SlotMetadata = Field(default_factory=SlotMetadata)
    chat_history: list[SlotChatMessage] = Field(default_factory=list)
    summary_buffer: SlotSummaryBuffer = Field(default_factory=SlotSummaryBuffer)
    environment_state: SlotEnvironmentState = Field(default_factory=SlotEnvironmentState)
    worldbook_context: SlotWorldbookContext = Field(default_factory=SlotWorldbookContext)


class SlotForkPayload(BaseModel):
    source_slot_id: str = ""
    target_slot_id: str = ""
    target_name: str = ""
    chat_index: int | None = None


class SlotSummaryBufferPayload(BaseModel):
    slot_id: str = ""
    content: str = ""
    source_message_count: int | None = None


class SlotVariablePatchPayload(BaseModel):
    slot_id: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)


class DynamicWorldbookPreviewPayload(BaseModel):
    slot_id: str = ""
    message: str = ""
    recent_window: int = 12


class ScenarioBundle(BaseModel):
    version: int = 1
    bundle_type: str = "campaign"
    exported_at: str = ""
    card_id: str = ""
    card_payload: dict[str, Any] = Field(default_factory=dict)
    worldbook_asset: dict[str, Any] = Field(default_factory=dict)
    slot_state: SlotState = Field(default_factory=SlotState)
    seed_memories: list[MemoryItemPayload] = Field(default_factory=list)
    settings_payload: dict[str, Any] = Field(default_factory=dict)
    preset_store: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    workshop_state: dict[str, Any] = Field(default_factory=dict)


class ScenarioBundleImportPayload(BaseModel):
    raw_json: str = ""
    target_slot_id: str = ""
    load_card: bool = True
