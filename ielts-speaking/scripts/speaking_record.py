#!/usr/bin/env python3
"""Save ChatGPT speaking exports locally; never calls a model or account API."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

CRITERIA = ('fc', 'lr', 'gra', 'pr')
ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')
MAX_BYTES = 2_000_000
MAX_RECORD_BYTES = 8_000_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text_value(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize(raw: dict) -> dict:
    """Validate an export and derive conservative, explicitly external scores."""
    require(isinstance(raw, dict), '练习导出必须是JSON对象')
    require(type(raw.get('schema_version')) is int and raw['schema_version'] == 1,
            '仅支持schema_version: 1')
    for key in ('record_id', 'session_id'):
        require(isinstance(raw.get(key), str) and bool(ID_PATTERN.fullmatch(raw[key])),
                f'{key}须为1—80位字母、数字、下划线或连字符，首位为字母或数字')
    require(isinstance(raw.get('date'), str), 'date须为YYYY-MM-DD')
    require(date.fromisoformat(raw['date']).isoformat() == raw['date'], 'date须为YYYY-MM-DD')
    require(raw.get('mode') in ('coach', 'mock'), 'mode须为coach或mock')
    require(raw.get('scope') in ('single_part', 'mixed_practice', 'full_mock'), 'scope无效')
    require(type(raw.get('full_mock_completed', False)) is bool, 'full_mock_completed须为布尔值')
    require(isinstance(raw.get('question_bank'), dict), '缺少question_bank来源信息')
    turns = raw.get('turns')
    require(isinstance(turns, list) and 0 < len(turns) <= 200, 'turns须包含1—200轮记录')
    ids = set()
    for turn in turns:
        require(isinstance(turn, dict), '每轮回答须为对象')
        require(text_value(turn.get('id')) and turn['id'] not in ids, '回答id缺失或重复')
        ids.add(turn['id'])
        require(type(turn.get('part')) is int and turn['part'] in (1, 2, 3), 'part须为1/2/3')
        require(text_value(turn.get('question')), '每轮须保存实际题目')
        require(turn.get('answer_status') in ('transcript', 'reconstruction', 'missing'),
                'answer_status须区分转写、回忆重构或缺失')
        require(turn.get('answer') is None or isinstance(turn['answer'], str), 'answer须为文字或null')
        require(turn.get('attempt') in ('first', 'repeat', 'assisted', 'unknown'), 'attempt无效')
    review = raw.get('assessment')
    require(isinstance(review, dict) and text_value(review.get('reviewer')), '缺少评分者')
    require(review.get('basis') in ('audio', 'transcript', 'unknown'), 'assessment.basis无效')
    require(review.get('audio_observed') is None or type(review['audio_observed']) is bool,
            'audio_observed须为true/false/null')
    require(review.get('model') is None or isinstance(review['model'], str), 'model须为文字或null')
    require(isinstance(review.get('scores'), dict), '缺少scores对象')
    fixes = review.get('priority_fixes', [])
    require(isinstance(fixes, list) and all(isinstance(x, str) for x in fixes), 'priority_fixes须为文字列表')
    require(review.get('next_practice') is None or isinstance(review['next_practice'], str),
            'next_practice须为文字或null')

    has_answers = any(t['answer_status'] == 'transcript' and text_value(t.get('answer')) for t in turns)
    audio_claimed = review['basis'] == 'audio' and review.get('audio_observed') is True
    scores, warnings = {}, []
    for key in CRITERIA:
        item = review['scores'].get(key, {})
        require(isinstance(item, dict), f'{key}须为band/evidence对象')
        band = item.get('band')
        require(band is None or (type(band) in (int, float) and 0 <= band <= 9
                and math.isfinite(band) and band * 2 == int(band * 2)), f'{key}分数须为0—9整分/半分或null')
        usable = (has_answers and text_value(item.get('evidence'))
                  and review['basis'] in ('audio', 'transcript'))
        if key in ('fc', 'pr'):
            usable = usable and audio_claimed
        scores[key] = band if usable else None
        if band is not None and not usable:
            warnings.append(f'{key}原报分保存在原始导出中；证据不足，不进入有效分数')
    complete = (raw['mode'] == 'mock' and raw['scope'] == 'full_mock'
                and raw.get('full_mock_completed') is True
                and {t['part'] for t in turns} == {1, 2, 3}
                and all(t['attempt'] == 'first' and t['answer_status'] == 'transcript'
                        and text_value(t.get('answer')) for t in turns)
                and all(scores[k] is not None for k in CRITERIA))
    overall = None
    if complete:
        mean = sum(Decimal(str(scores[k])) for k in CRITERIA) / Decimal(4)
        overall = float((mean * 2).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / 2)
    else:
        warnings.append('未满足完整独立口语模拟及四维证据条件，overall_estimate留空')
    return {
        'scores': scores, 'overall_estimate': overall,
        'score_source': 'external_ai_feedback', 'verification_status': 'model_inference',
        'audio_observed_by_external_reviewer': review.get('audio_observed'),
        'audio_reviewed_locally': False, 'has_answer_record': has_answers,
        'warnings': warnings,
    }


def read_json(path: Path, max_bytes: int = MAX_BYTES) -> dict:
    require(not path.is_symlink(), '不读取符号链接记录文件')
    with path.open('rb') as stream:
        content = stream.read(max_bytes + 1)
    require(len(content) <= max_bytes, '输入或记录过大，请按一次练习拆分')
    value = json.loads(content)
    require(isinstance(value, dict), 'JSON根须为对象')
    return value


def fingerprint(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError('记录目录不能是符号链接')
    if not path.exists():
        private_directory(path.parent)
        path.mkdir(mode=0o700, exist_ok=True)
    require(path.is_dir(), '数据路径不是目录')


def records_directory(root: Path) -> Path:
    for path in (root, root / 'speaking', root / 'speaking' / 'records'):
        require(not path.is_symlink(), '学习根或口语记录路径不能是符号链接')
    return root / 'speaking' / 'records'


def save_record(raw: dict, root: Path) -> dict:
    result = normalize(raw)
    record_dir = records_directory(root)
    path = record_dir / (raw['record_id'] + '.json')
    digest = fingerprint(raw)
    envelope = {'type': 'speaking-practice', 'imported_at': datetime.now(timezone.utc).isoformat(),
                'source_sha256': digest, 'source_payload': raw, 'normalized': result}
    encoded = (json.dumps(envelope, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    require(len(encoded) <= MAX_RECORD_BYTES, '生成记录过大，尚未保存')
    private_directory(record_dir)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = read_json(path, MAX_RECORD_BYTES)
        if existing.get('source_sha256') == digest and existing.get('source_payload') == raw:
            return {'action': 'duplicate', 'path': str(path), 'normalized': result}
        raise ValueError('同record_id内容不同，原件未覆盖；更正时使用新record_id并保留原session_id') from None
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
    return {'action': 'saved', 'path': str(path), 'normalized': result}


def summarize(root: Path) -> dict:
    record_dir = records_directory(root)
    sessions, invalid = {}, []
    count = 0
    for path in sorted(record_dir.glob('*.json')):
        try:
            item = read_json(path, MAX_RECORD_BYTES)
            raw = item['source_payload']
            normalized = normalize(raw)  # Never trust cached or imported normalized scores.
            require(item.get('type') == 'speaking-practice', '记录类型不符')
            require(item.get('source_sha256') == fingerprint(raw), '记录哈希不符')
            imported = item.get('imported_at')
            require(isinstance(imported, str), '缺少导入时间')
            imported_time = datetime.fromisoformat(imported)
            require(imported_time.tzinfo is not None, '导入时间缺少时区')
            count += 1
            key = raw['session_id']
            if key not in sessions or imported_time > sessions[key][0]:
                sessions[key] = (imported_time, {
                    'session_id': key, 'record_id': raw['record_id'], 'date': raw['date'],
                    'mode': raw['mode'], 'scope': raw['scope'],
                    'reviewer': raw['assessment']['reviewer'], 'model': raw['assessment'].get('model'),
                    'basis': raw['assessment']['basis'], 'path': str(path),
                    'next_practice': raw['assessment'].get('next_practice'),
                    'priority_fixes': raw['assessment'].get('priority_fixes', []), **normalized,
                })
        except (ValueError, OSError, KeyError, TypeError) as error:
            invalid.append({'path': str(path), 'error': str(error)})
    ordered = [entry for _, entry in sorted(sessions.values(), key=lambda x: x[0], reverse=True)]
    return {'record_count': count, 'session_count': len(ordered),
            'sessions_with_answers': sum(x['has_answer_record'] for x in ordered),
            'sessions': ordered, 'invalid_files': invalid}


def resolve_root(explicit: str | None) -> Path:
    selected = explicit or os.environ.get('IELTS_COACH_HOME')
    if not selected:
        config = Path.home() / '.config/bandwise/config.json'
        if config.exists():
            selected = read_json(config).get('data_root')
    require(selected is None or text_value(selected), 'data_root须为路径文字')
    return Path(selected or '~/ielts-coach').expanduser().absolute()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', help='私人学习目录；优先于环境变量和本机配置')
    commands = parser.add_subparsers(dest='command', required=True)
    importer = commands.add_parser('import', help='预览一个JSON导出；--save才保存')
    importer.add_argument('file', type=Path)
    importer.add_argument('--save', action='store_true')
    commands.add_parser('status', help='只读汇总口语记录；更正不增加场次')
    args = parser.parse_args(argv)
    try:
        root = resolve_root(args.root)
        if args.command == 'status':
            output = summarize(root)
        else:
            raw = read_json(args.file)
            output = save_record(raw, root) if args.save else {'action': 'preview', 'normalized': normalize(raw)}
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print(f'错误：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
