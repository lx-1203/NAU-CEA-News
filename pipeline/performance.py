"""Shared cues and repetition audit. Rules are an editorial fallback, not NLU."""
import math
from collections import Counter

COMMON_STATES = ('normal', 'happy', 'surprised', 'thinking', 'serious', 'presenting', 'thumbsup', 'wave')
FREQUENT_STATES = ('normal', 'happy', 'presenting', 'thinking')
ASSET_VARIANTS = {state: (state, state+'2', state+'3') if state in FREQUENT_STATES else (state,)
                  for state in COMMON_STATES}
INTENTS = {
    'neutral': ('normal', 'presenting'), 'explain': ('presenting', 'normal'),
    'analysis': ('thinking', 'presenting'), 'caution': ('serious',),
    'positive': ('happy', 'thumbsup'), 'surprise': ('surprised',), 'greet': ('wave',),
}
FIELDS = {'intent', 'expression', 'base', 'action', 'focus_ratio', 'reason'}


def semantic_state(expression):
    for state, variants in ASSET_VARIANTS.items():
        if expression in variants:
            return state
    return expression  # Legacy optional expressions remain distinct.


def infer_intent(line, story):
    text = line['text']
    if line['scene'] < 0 and any(t in text for t in ['欢迎', '大家好', '再见', '我是']):
        return 'greet', '首尾问候'
    if any(t in text for t in ['尚未', '仍需', '无法', '限制', '风险', '失败', '漏洞', '未公开', '尚待', '不代表']):
        return 'caution', '本句限制或风险'
    if any(t in text for t in ['为什么', '如何', '意味着', '原因', '相比', '区别', '需要', '计划', '验证', '申请', '安排', '关注']):
        return 'analysis', '本句分析、计划或条件'
    if any(t in text for t in ['用于', '通过', '支持', '提供', '采用', '可以', '帮助', '包含', '接口', '方法']):
        return 'explain', '本句说明机制或功能'
    if any(t in story.get('title', '') for t in ['方法', '研究', '模型', '工具', '开源']):
        return 'explain', '条目背景为技术说明'
    return 'neutral', '平稳事实播报'


def validate_choice(choice):
    if choice['intent'] not in INTENTS:
        raise ValueError('未知表演意图')
    ratio = choice['focus_ratio']
    if (isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or
            not math.isfinite(ratio) or not 0 < ratio < 1):
        raise ValueError('表演触发比例无效')
    if choice['action'] not in {'hold', 'nod', 'greet'}:
        raise ValueError('未知表演动作')
    if not any(choice['base'] in variants for variants in ASSET_VARIANTS.values()):
        raise ValueError('未知基础表情')
    if not isinstance(choice['expression'], str):
        raise ValueError('表情必须为名称')


def plan_performances(lines, stories, overrides=None):
    overrides = {} if overrides is None else overrides
    if not isinstance(overrides, dict) or any(k not in {str(i) for i in range(len(lines))} for k in overrides):
        raise ValueError('表演覆盖必须使用有效句序号')
    result, histories, variant_positions = [], {}, Counter()
    for index, line in enumerate(lines):
        anchor, scene = line['anchor'], line['scene']
        if anchor not in {'xiaoXu', 'xiaoHe'}:
            raise ValueError('未知主播')
        override = overrides.get(str(index), {})
        if not isinstance(override, dict) or set(override) - FIELDS:
            raise ValueError('未知表演配置字段')
        story = stories[scene] if 0 <= scene < len(stories) else {}
        intent, reason = infer_intent(line, story)
        intent = override.get('intent', intent)
        if intent not in INTENTS:
            raise ValueError('未知表演意图')
        candidates = INTENTS[intent]
        history = histories.setdefault(anchor, [])
        focus = candidates[0]
        if len(history) >= 2 and history[-2:] == [focus, focus] and len(candidates) > 1:
            focus = candidates[1]
        ordinal = len(history)
        action = 'greet' if intent == 'greet' else 'nod' if intent in {'explain', 'positive', 'analysis'} and ordinal % 3 == 0 else 'hold'
        expression = ASSET_VARIANTS[focus][variant_positions[anchor, focus] % len(ASSET_VARIANTS[focus])]
        base = expression if focus == 'normal' else ASSET_VARIANTS['normal'][ordinal % 3]
        choice = dict(intent=intent, expression=expression, base=base, action=action,
                      focus_ratio=(.30, .44, .56)[ordinal % 3], reason=reason)
        choice.update(override)
        if override:
            choice['reason'] = override.get('reason', '编辑逐句指定')
        validate_choice(choice)
        category = semantic_state(choice['expression'])
        history.append(category)
        if category in ASSET_VARIANTS and choice['expression'] in ASSET_VARIANTS[category]:
            variant_positions[anchor, category] = (ASSET_VARIANTS[category].index(choice['expression']) + 1) % len(ASSET_VARIANTS[category])
        result.append(choice)
    return result


def performance_audit(shots):
    """Report skew rather than forcing a quota of emotional faces."""
    anchors, warnings = {}, []
    for anchor in ['xiaoXu', 'xiaoHe']:
        selected = [s['performance'] for s in shots if s['anchor'] == anchor and s.get('scene', -1) >= 0]
        states = [semantic_state(p['expression']) for p in selected]
        counts = Counter(states)
        longest = run = 0
        prior = None
        for state in states:
            run = run + 1 if state == prior else 1
            prior = state
            longest = max(longest, run)
        share = max(counts.values(), default=0) / max(len(states), 1)
        anchors[anchor] = dict(cues=len(states), states=dict(counts), variants=dict(Counter(p['expression'] for p in selected)), longest_run=longest,
                               dominant_share=round(share, 4), actions=dict(Counter(p['action'] for p in selected)))
        if len(states) >= 8 and (share > .70 or longest > 5):
            warnings.append(f'{anchor}: 表情占比或连续重复偏高，请结合新闻内容复核')
    return dict(common_states=list(COMMON_STATES), anchors=anchors, warnings=warnings,
                interpretation='统计是编辑复核提示，不要求凑齐所有情绪；默认规则不等同完整语义理解')
