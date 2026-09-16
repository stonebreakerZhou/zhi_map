import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react';

type Step = { title: string; text: string; target?: string; placement?: 'top' | 'bottom' | 'left' | 'right' };
type Geometry = { spotlight?: { left: number; top: number; width: number; height: number }; card: { left: number; top: number }; arrow?: CSSProperties };

const steps: Step[] = [
  { title: '欢迎来到知树', text: '这里以极简对话为主，需要梳理思路时再进入图谱。用四个提示快速认识核心操作。' },
  { title: '从一个问题开始', text: '点击这里创建新问题。模型配置完成后，你也可以直接在底部输入框继续提问。', target: '.onboarding .primary', placement: 'top' },
  { title: '从回答中展开讨论', text: '选中回答里的任意文字，会出现“展开讨论”。新讨论保留精确原文，并成为图谱中的分支。', target: '.chat', placement: 'right' },
  { title: '按需探索图谱', text: '图谱不是聊天的必经步骤。需要回看主线、分支和关系时，再从这里进入。', target: '.mode-toggle', placement: 'bottom' },
  { title: '模型与知识都在设置中', text: '从左下角账户菜单进入设置中心，管理服务商、默认模型、主题、本地知识库和数据备份。', target: '#conversation-actions-button', placement: 'top' },
];

const margin = 16, gap = 14, spotlightGap = 7;
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function TutorialOverlay({ open, close }: { open: boolean; close: () => void }) {
  const [step, setStep] = useState(0), [geometry, setGeometry] = useState<Geometry>({ card: { left: 0, top: 0 } });
  const cardRef = useRef<HTMLDivElement>(null);
  const current = steps[step];

  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const card = cardRef.current;
      if (!card) return;
      const cardWidth = card.offsetWidth, cardHeight = card.offsetHeight;
      let element = current.target ? document.querySelector<HTMLElement>(current.target) : null;
      if (current.target === '#conversation-actions-button' && (!element || !element.getClientRects().length)) element = document.querySelector<HTMLElement>('#nav-toggle');
      const target = element?.getBoundingClientRect();
      const visible = target && target.width > 0 && target.height > 0 && target.bottom > 0 && target.right > 0 && target.top < innerHeight && target.left < innerWidth;
      if (!visible || !target) {
        setGeometry({ card: { left: clamp((innerWidth - cardWidth) / 2, margin, innerWidth - cardWidth - margin), top: clamp((innerHeight - cardHeight) / 2, margin, innerHeight - cardHeight - margin) } });
        return;
      }
      const spotLeft = clamp(target.left - spotlightGap, 8, innerWidth - 8);
      const spotTop = clamp(target.top - spotlightGap, 8, innerHeight - 8);
      const spotRight = clamp(target.right + spotlightGap, spotLeft, innerWidth - 8);
      const spotBottom = clamp(target.bottom + spotlightGap, spotTop, innerHeight - 8);
      const spot = { left: spotLeft, top: spotTop, width: spotRight - spotLeft, height: spotBottom - spotTop };
      const candidates = {
        bottom: { left: target.left + target.width / 2 - cardWidth / 2, top: target.bottom + gap },
        top: { left: target.left + target.width / 2 - cardWidth / 2, top: target.top - cardHeight - gap },
        right: { left: target.right + gap, top: target.top + target.height / 2 - cardHeight / 2 },
        left: { left: target.left - cardWidth - gap, top: target.top + target.height / 2 - cardHeight / 2 },
      };
      const fits = (value: { left: number; top: number }) => value.left >= margin && value.top >= margin && value.left + cardWidth <= innerWidth - margin && value.top + cardHeight <= innerHeight - margin;
      const order = [current.placement ?? 'bottom', 'bottom', 'top', 'right', 'left'] as const;
      const chosenName = order.find(name => fits(candidates[name])) ?? 'bottom';
      const chosen = candidates[chosenName];
      const cardPosition = { left: clamp(chosen.left, margin, innerWidth - cardWidth - margin), top: clamp(chosen.top, margin, innerHeight - cardHeight - margin) };
      const arrow: CSSProperties = chosenName === 'bottom' ? { top: -7, left: clamp(target.left + target.width / 2 - cardPosition.left - 7, 24, cardWidth - 38) }
        : chosenName === 'top' ? { bottom: -7, left: clamp(target.left + target.width / 2 - cardPosition.left - 7, 24, cardWidth - 38) }
        : chosenName === 'right' ? { left: -7, top: clamp(target.top + target.height / 2 - cardPosition.top - 7, 24, cardHeight - 38) }
        : { right: -7, top: clamp(target.top + target.height / 2 - cardPosition.top - 7, 24, cardHeight - 38) };
      setGeometry({ spotlight: spot, card: cardPosition, arrow });
    };
    const frame = requestAnimationFrame(update);
    const observer = new ResizeObserver(update);
    if (cardRef.current) observer.observe(cardRef.current);
    addEventListener('resize', update); addEventListener('scroll', update, true);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); removeEventListener('resize', update); removeEventListener('scroll', update, true); };
  }, [open, step, current]);

  if (!open) return null;
  const finish = () => { localStorage.setItem('zhishu-tutorial-complete', '1'); close(); };
  const spot = geometry.spotlight;
  return <div className="tutorial-overlay" role="dialog" aria-modal="true" aria-label="知树新手教程">
    {spot && <><div className="tutorial-mask mask-top" style={{ height: spot.top }} /><div className="tutorial-mask mask-left" style={{ top: spot.top, width: spot.left, height: spot.height }} /><div className="tutorial-mask mask-right" style={{ top: spot.top, left: spot.left + spot.width, height: spot.height }} /><div className="tutorial-mask mask-bottom" style={{ top: spot.top + spot.height }} /><div className="tutorial-spotlight" style={spot} /></>}
    {!spot && <div className="tutorial-mask mask-full" />}
    <div ref={cardRef} className={`tutorial-card ${spot ? 'anchored' : 'welcome'}`} style={{ left: geometry.card.left, top: geometry.card.top }}>
      {geometry.arrow && <span className="tutorial-arrow" style={geometry.arrow} />}
      <div className="tutorial-progress">{steps.map((_, index) => <span key={index} className={index <= step ? 'active' : ''} />)}</div>
      <p className="settings-eyebrow">{step === 0 ? '开始使用' : `${step} / ${steps.length - 1}`}</p><h2>{current.title}</h2><p>{current.text}</p>
      <div className="tutorial-actions"><button onClick={finish}>跳过</button>{step > 0 && <button onClick={() => setStep(step - 1)}>上一步</button>}<button className="primary" onClick={() => step === steps.length - 1 ? finish() : setStep(step + 1)}>{step === steps.length - 1 ? '完成' : step === 0 ? '开始导览' : '下一步'}</button></div>
    </div>
  </div>;
}
