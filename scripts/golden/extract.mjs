process.env.TZ = 'Asia/Seoul'; // 시안 scMakeDays 는 new Date('YYYY-MM-DD')(UTC 자정)를 현지 getDay 로 읽는다. 기계 시간대와 무관하게 고정한다
// golden 추출(Design 5절 17). 시안/관리자.html 에서 상수 줄과 일정 함수 8개 줄만 이름으로 찾아 node:vm 에서 돌린다.
// 입력은 아래 합성 사례뿐이라 사람·회사 이름이 없다. 출력은 사례 id·숫자·날짜(ISO)·시각이다.
// 키 정렬 · 2칸 들여쓰기 · 끝 줄바꿈 JSON 을 stdout 으로 낸다. 대조는 scripts/golden/check.sh 한 곳이다.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const ROOT = new URL('../../', import.meta.url);
const SOURCE = new URL('시안/관리자.html', ROOT);
const NAMES = ['scHm', 'scM2', 'scDay', 'scLunch', 'scSkip', 'scTime', 'scBySlot', 'scMakeDays'];

function pickLines(html) {
  const lines = html.split('\n');
  const one = (prefix) => {
    const hit = lines.filter((l) => l.startsWith(prefix));
    if (hit.length !== 1) throw new Error(`시안에서 "${prefix}" 줄이 ${hit.length}개다(1개여야 한다)`);
    return hit[0];
  };
  return [one('const SC_SLOT='), ...NAMES.map((n) => one(`function ${n}(`))].join('\n');
}

const ctx = vm.createContext({});
vm.runInContext(pickLines(readFileSync(SOURCE, 'utf8')), ctx, { filename: '시안/관리자.html' });
const { scMakeDays, scTime } = vm.runInContext('({ scMakeDays, scTime })', ctx);

// ── make_days 사례: 시작 요일(월·금·토·일) · n(0·1·4·5·10) · 월말·연말 넘김 · 60일 가드
const MAKE_DAYS = [
  ['md-mon-n0', '2026-11-02', 0],
  ['md-mon-n1', '2026-11-02', 1],
  ['md-mon-n4', '2026-11-02', 4],
  ['md-fri-n5', '2026-11-06', 5],
  ['md-sat-n1', '2026-11-07', 1],
  ['md-sun-n4', '2026-11-08', 4],
  ['md-monthend-n5', '2026-11-26', 5],
  ['md-yearend-n10', '2026-12-28', 10],
  ['md-guard-sat-n45', '2026-11-07', 45], // 60일 안의 평일 42개까지만 나온다(day_count 상한 40 은 안에 든다)
];

function makeDaysCase([id, start, n]) {
  const input = { start, n, start_time: '13:00', end_time: '17:00' };
  const out = scMakeDays(start, n, input.start_time, input.end_time).map((d) => ({
    no: d.no,
    date: d.date.replace(/\./g, '-'),
    start: d.start,
    end: d.end,
  }));
  return { id, in: input, out };
}

// ── session_time 사례. 세션 칸: [id, 섹션 번호, day_no, slot, minutes, time_start, time_end]
const day = (no, start, end, lunch_start = null, lunch_end = null) => ({ no, start, end, lunch_start, lunch_end });
const PM = day(1, '13:00', '17:00');
const SESSION_TIME = [
  ['st-pm-4-slots', 50, 10, [PM], [[1, 1, 1, 1], [2, 1, 1, 2], [3, 1, 1, 3], [4, 1, 1, 4]]],
  ['st-slot60-break0', 60, 0, [PM], [[1, 1, 1, 1], [2, 1, 1, 2], [3, 1, 1, 3], [4, 1, 1, 4]]],
  ['st-lunch-1200-1300', 50, 10, [day(1, '09:00', '18:00', '12:00', '13:00')],
    [[1, 1, 1, 1], [2, 1, 1, 2], [3, 1, 1, 3], [4, 1, 1, 4], [5, 1, 1, 5], [6, 1, 1, 6]]],
  ['st-lunch-straddle-90', 50, 10, [day(1, '09:00', '18:00', '12:00', '13:00')],
    [[1, 1, 1, 1, 90], [2, 1, 1, 2], [3, 1, 1, 3], [4, 1, 1, 4]]],
  ['st-lunch-outside-day', 50, 10, [day(1, '13:00', '17:00', '12:00', '13:00')], [[1, 1, 1, 1], [2, 1, 1, 2]]],
  ['st-lunch-mid-afternoon', 50, 10, [day(1, '13:00', '17:00', '14:30', '15:00')],
    [[1, 1, 1, 1], [2, 1, 1, 2], [3, 1, 1, 3]]],
  ['st-mixed-90-50', 50, 10, [PM], [[1, 1, 1, 1, 90], [2, 1, 1, 2, 50], [3, 1, 1, 3], [4, 1, 1, 4, 0]]],
  ['st-exception-time', 50, 10, [PM],
    [[1, 1, 1, 1], [2, 1, 1, 2, null, '10:00', '11:30'], [3, 1, 1, 3], [4, 1, null, null, null, '09:00', '09:40']]],
  ['st-clip-day-end', 50, 10, [PM], [[1, 1, 1, 1, 90], [2, 1, 1, 2, 90], [3, 1, 1, 3, 90], [4, 1, 1, 4]]],
  ['st-same-slot', 50, 10, [PM], [[1, 1, 1, 1], [2, 1, 1, 2], [3, 1, 1, 2], [4, 1, 1, 3]]],
  ['st-slot-gap', 50, 10, [PM], [[1, 1, 1, 1], [2, 1, 1, 3], [3, 1, 1, 5]]],
  ['st-null-no-slot-no-day', 50, 10, [PM], [[1, 1, 1, 1], [2, 1, 1, null], [3, 1, null, null], [4, 1, 2, 1]]],
  ['st-sections-and-days', 50, 10, [PM, day(2, '09:00', '12:00')],
    [[1, 1, 1, 1], [2, 1, 1, 2], [3, 2, 1, 1], [4, 2, 1, 2], [5, 1, 2, 1], [6, 1, 2, 2]]],
  ['st-defaults-null', null, null, [PM], [[1, 1, 1, 1], [2, 1, 1, 2]]],
];

function sessionTimeCase([id, slotMin, breakMin, days, rows]) {
  const sessions = rows.map(([sid, section, day_no, slot = null, minutes = null, time_start = null, time_end = null]) => ({
    id: sid, section, day_no, slot, minutes, time_start, time_end,
  }));
  // 시안 모양: c.days[{no,start,end,lunch}] · c.sections[{sessions[{id,day,slot,minutes,time}]}]
  const toMock = (s) => ({
    id: s.id, day: s.day_no, slot: s.slot, minutes: s.minutes,
    ...(s.time_start ? { time: { start: s.time_start, end: s.time_end } } : {}),
  });
  const mocks = new Map(sessions.map((s) => [s.id, toMock(s)]));
  const sectionNos = [...new Set(sessions.map((s) => s.section))];
  const c = {
    slotMin: slotMin, breakMin: breakMin,
    days: days.map((d) => ({ no: d.no, start: d.start, end: d.end, ...(d.lunch_start ? { lunch: { start: d.lunch_start, end: d.lunch_end } } : {}) })),
    sections: sectionNos.map((no) => ({ sessions: sessions.filter((s) => s.section === no).map((s) => mocks.get(s.id)) })),
  };
  const out = sessions.map((s) => {
    const t = scTime(c, mocks.get(s.id));
    return { id: s.id, time: t ? { start: t.start, end: t.end } : null };
  });
  return { id, in: { slot_min: slotMin, break_min: breakMin, days, sessions }, out };
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    return Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])]));
  }
  return v;
}

const golden = { make_days: MAKE_DAYS.map(makeDaysCase), session_time: SESSION_TIME.map(sessionTimeCase) };
process.stdout.write(JSON.stringify(sortKeys(golden), null, 2) + '\n');
