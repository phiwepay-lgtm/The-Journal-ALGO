import { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
} from 'lightweight-charts';

export default function Chart({ data, useHA = false, priceFormat }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data?.candles?.length) return undefined;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#0b121a' },
        textColor: '#8190a3',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: 'rgba(75, 93, 112, 0.13)' },
        horzLines: { color: 'rgba(75, 93, 112, 0.13)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#63748a', labelBackgroundColor: '#344255' },
        horzLine: { color: '#63748a', labelBackgroundColor: '#344255' },
      },
      rightPriceScale: {
        borderColor: 'rgba(99, 116, 138, 0.25)',
      },
      timeScale: {
        borderColor: 'rgba(99, 116, 138, 0.25)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 4,
        barSpacing: 7,
      },
      localization: {
        locale: 'en-ZA',
        timeFormatter: (timestamp) => new Date(timestamp * 1000).toLocaleString('en-ZA', {
          month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
        }),
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#20c997',
      downColor: '#f05d6f',
      wickUpColor: '#20c997',
      wickDownColor: '#f05d6f',
      borderVisible: false,
      priceFormat: {
        type: 'price',
        precision: priceFormat?.precision ?? 2,
        minMove: priceFormat?.min_move ?? 0.01,
      },
    });

    const source = useHA ? data.ha_candles : data.candles;
    series.setData(source.map(({ time, open, high, low, close }) => ({
      time, open, high, low, close,
    })));
    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [data, useHA, priceFormat]);

  return <div className="chart-canvas" ref={containerRef} aria-label="Trading candlestick chart" />;
}
