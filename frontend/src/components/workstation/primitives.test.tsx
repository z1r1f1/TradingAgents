import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { EmptyState, Field, InfoBlock, MetricCard, MiniStat, Notice, StatusBadge } from './primitives';
import { MemoryPicker } from './memory-picker';
import type { AgentMemory } from '../../api';

describe('workstation primitives', () => {
  it('renders presentation-only cards and notices', () => {
    const html = renderToStaticMarkup(
      <>
        <MiniStat label="运行模式" value="local" />
        <MetricCard label="历史分析" value={3} detail="当前工作区记录" />
        <Notice tone="amber">注意事项</Notice>
        <StatusBadge status="pending" formatStatusLabel={status => status === 'pending' ? '等待中' : String(status)} />
        <EmptyState title="暂无数据" description="稍后再试" />
        <InfoBlock title="附加信息"><span>内容</span></InfoBlock>
        <Field label="邮箱"><input value="demo@example.com" readOnly /></Field>
      </>
    );

    expect(html).toContain('运行模式');
    expect(html).toContain('历史分析');
    expect(html).toContain('注意事项');
    expect(html).toContain('等待中');
    expect(html).toContain('暂无数据');
    expect(html).toContain('附加信息');
    expect(html).toContain('demo@example.com');
  });

  it('renders memory labels without depending on App exports', () => {
    const memory: AgentMemory = {
      id: 1,
      title: '记忆标题',
      content: '内容',
      ticker: 'SPY',
      analysis_date: '2026-05-01',
      source_analysis_task_id: 7,
      agent_name: 'Market Analyst',
      archived: false,
      user_id: 42,
      created_at: '2026-05-01T00:00:00Z',
      tags: {}
    };

    const html = renderToStaticMarkup(
      <MemoryPicker title="附加记忆" memories={[memory]} selectedIds={[1]} onToggle={() => undefined} />
    );

    expect(html).toContain('附加记忆');
    expect(html).toContain('市场分析师 · SPY · 2026-05-01');
    expect(html).toContain('checked');
  });
});
