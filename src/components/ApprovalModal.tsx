import React, { useState } from 'react';
import { ShieldAlert, X } from 'lucide-react';
import { formatINR } from '../utils/formatters';

interface OrderDraft {
  symbol: string;
  exchange: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  stop_loss: number;
  target: number;
  product: 'MIS' | 'CNC';
  order_type: 'LIMIT' | 'MARKET';
  broker: string;
  mode: 'paper' | 'live';
}

interface Props {
  open: boolean;
  order: OrderDraft | null;
  preview: any;
  onClose: () => void;
  onConfirm: (approved: boolean) => Promise<void>;
  submitting: boolean;
}

export const ApprovalModal: React.FC<Props> = ({
  open,
  order,
  preview,
  onClose,
  onConfirm,
  submitting,
}) => {
  const [acknowledged, setAcknowledged] = useState(false);

  if (!open || !order) return null;

  const isLive = order.mode === 'live' && order.broker !== 'paper';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
      <div className="w-full max-w-lg bg-[#0f1626] border border-slate-700 rounded-lg overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className={`w-5 h-5 ${isLive ? 'text-amber-400' : 'text-sky-400'}`} />
            <h3 className="font-display font-semibold text-base text-slate-100">
              {isLive ? 'Live Broker Order Confirmation' : 'Paper Order Execution Review'}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-100 rounded"
            aria-label="Close confirmation dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4 text-sm">
          {isLive && (
            <div className="p-3 bg-amber-950/40 border border-amber-700/50 rounded text-amber-200 text-xs">
              Live order dispatch selected for <strong>{order.broker.toUpperCase()}</strong>. Verify all 7 mandatory risk fields before approving.
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 bg-[#0a0f1c] border border-slate-800 rounded p-4 font-mono text-xs">
            <div>
              <div className="text-slate-400 mb-0.5">1. Complete Order</div>
              <div className="text-slate-100 font-semibold">
                {order.side} · {order.exchange}:{order.symbol} · {order.product} ({order.order_type})
              </div>
            </div>
            <div>
              <div className="text-slate-400 mb-0.5">2. Quantity</div>
              <div className="text-slate-100 font-semibold">{order.quantity} Shares</div>
            </div>
            <div>
              <div className="text-slate-400 mb-0.5">3. Entry Price</div>
              <div className="text-slate-100 font-semibold">{formatINR(order.price)}</div>
            </div>
            <div>
              <div className="text-slate-400 mb-0.5">4. Stop-Loss</div>
              <div className="text-rose-400 font-semibold">{formatINR(order.stop_loss)}</div>
            </div>
            <div>
              <div className="text-slate-400 mb-0.5">5. Target</div>
              <div className="text-emerald-400 font-semibold">{formatINR(order.target)}</div>
            </div>
            <div>
              <div className="text-slate-400 mb-0.5">6. Max Estimated Loss</div>
              <div className="text-rose-400 font-semibold">
                {formatINR(preview?.maximum_estimated_loss_inr ?? Math.abs(order.price - order.stop_loss) * order.quantity)}
              </div>
            </div>
          </div>

          <label className="flex items-start gap-2.5 text-xs text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-0.5 rounded border-slate-600 bg-slate-900"
            />
            <span>
              7. I explicitly confirm the order symbol, quantity, entry price, stop-loss, target, and maximum INR loss above.
            </span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-3.5 border-t border-slate-800 bg-[#0b101b]">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-300 border border-slate-700 rounded hover:bg-slate-800 whitespace-nowrap"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!acknowledged || submitting}
            onClick={() => onConfirm(true)}
            className="px-4 py-2 text-xs font-semibold text-slate-950 bg-emerald-400 hover:bg-emerald-300 disabled:opacity-40 rounded whitespace-nowrap"
          >
            {submitting ? 'Submitting...' : isLive ? 'Approve & Send Live Order' : 'Confirm Paper Order'}
          </button>
        </div>
      </div>
    </div>
  );
};
