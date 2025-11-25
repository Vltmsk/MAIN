"use client";

interface ExchangeFilterProps {
  exchange: string;
  market: "spot" | "futures";
  enabled: boolean;
  onToggle: (exchange: string, market: "spot" | "futures", enabled: boolean) => void;
}

export default function ExchangeFilter({ exchange, market, enabled, onToggle }: ExchangeFilterProps) {
  const exchangeNames: Record<string, string> = {
    binance: "Binance",
    bybit: "Bybit",
    bitget: "Bitget",
    gate: "Gate",
    hyperliquid: "Hyperliquid",
  };

  const marketNames: Record<string, string> = {
    spot: "Spot",
    futures: "Futures",
  };

  const exchangeName = exchangeNames[exchange] || exchange;
  const marketName = marketNames[market] || market;

  return (
    <div className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg hover:bg-zinc-800 transition-colors">
      <div className="flex items-center gap-3">
        <span className="text-white font-medium text-sm">{exchangeName}</span>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${
            market === "spot"
              ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
              : "bg-blue-500/10 border-blue-500/40 text-blue-300"
          }`}
        >
          {marketName}
        </span>
      </div>
      <div
        className={`w-12 h-6 rounded-full transition-colors cursor-pointer ${
          enabled ? "bg-emerald-500" : "bg-zinc-600"
        }`}
        onClick={() => onToggle(exchange, market, !enabled)}
      >
        <div
          className={`w-5 h-5 bg-white rounded-full transition-transform mt-0.5 ${
            enabled ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </div>
    </div>
  );
}

