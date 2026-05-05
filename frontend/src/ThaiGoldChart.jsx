import React, { useState, useEffect, useRef } from "react";
import { Line } from "react-chartjs-2";
import Chart from "chart.js/auto";
import 'chartjs-adapter-date-fns';

const FIXED_WINDOW_MINUTES = 240;
const STEP_MINUTES = 5;
const REFRESH_INTERVAL_MS = 60 * 1000;

function parseLocalTimestamp(timestamp) {
  if (!timestamp || typeof timestamp !== "string") return null;

  const exactMatch = timestamp.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
  const shortMatch = timestamp.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);

  if (exactMatch) {
    const [datePart, timePart] = timestamp.split("T");
    const [year, month, day] = datePart.split("-").map(Number);
    const [hour, minute, second] = timePart.split(":").map(Number);
    return new Date(year, month - 1, day, hour, minute, second);
  }

  if (shortMatch) {
    const [datePart, timePart] = timestamp.split("T");
    const [year, month, day] = datePart.split("-").map(Number);
    const [hour, minute] = timePart.split(":").map(Number);
    return new Date(year, month - 1, day, hour, minute, 0);
  }

  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function roundDownTo5Minutes(date) {
  const cloned = new Date(date);
  const minutes = cloned.getMinutes();
  const floored = Math.floor(minutes / STEP_MINUTES) * STEP_MINUTES;
  cloned.setMinutes(floored, 0, 0);
  return cloned;
}

function buildTimeLabels(endTime) {
  const labels = [];
  const startTime = new Date(endTime.getTime() - FIXED_WINDOW_MINUTES * 60_000);
  for (let cursor = new Date(startTime); cursor.getTime() <= endTime.getTime(); cursor.setMinutes(cursor.getMinutes() + STEP_MINUTES)) {
    labels.push(new Date(cursor));
  }
  return labels;
}

function getMsToNextMinute() {
  const now = new Date();
  const target = new Date(now);
  target.setSeconds(0, 0);
  target.setMinutes(target.getMinutes() + 1);
  return target.getTime() - now.getTime();
}

function normalizeChartData(raw) {
  const normalized = raw.reduce((acc, item) => {
    const timestamp = parseLocalTimestamp(item.timestamp);
    const price = Number(item.price);
    if (!timestamp || Number.isNaN(price)) return acc;
    const rounded = roundDownTo5Minutes(timestamp).getTime();
    acc.push({ timestamp: rounded, price });
    return acc;
  }, []);

  const endTime = roundDownTo5Minutes(new Date());
  const labels = buildTimeLabels(endTime);

  if (labels.length === 0) {
    return { labels: [], prices: [], latestRaw: null };
  }

  normalized.sort((a, b) => a.timestamp - b.timestamp);
  const priceMap = new Map();
  normalized.forEach((point) => priceMap.set(point.timestamp, point.price));

  const firstLabelTime = labels[0].getTime();
  let lastKnownPrice = null;
  const priorPoints = normalized.filter((point) => point.timestamp < firstLabelTime);
  if (priorPoints.length > 0) {
    lastKnownPrice = priorPoints[priorPoints.length - 1].price;
  } else {
    const firstInside = normalized.find((point) => point.timestamp >= firstLabelTime && point.timestamp <= endTime.getTime());
    if (firstInside) lastKnownPrice = firstInside.price;
  }

  const prices = labels.map((label) => {
    const timestamp = label.getTime();
    const price = priceMap.has(timestamp) ? priceMap.get(timestamp) : lastKnownPrice;
    if (price != null) lastKnownPrice = price;
    return price != null ? price : 0;
  });

  return { labels, prices, latestRaw: normalized.length ? normalized[normalized.length - 1] : null };
}

export default function ThaiGoldChart({ onPriceUpdate }) {
  const chartRef = useRef();
  const [chartLabels, setChartLabels] = useState([]);
  const [chartPrices, setChartPrices] = useState([]);

  useEffect(() => {
    let intervalId = null;
    let timeoutId = null;

    const fetchChartData = async () => {
      try {
        const res = await fetch(`/api/chart?t=${Date.now()}`);
        const json = await res.json();
        if (!json || json.status !== "success" || !Array.isArray(json.data)) return;

        const { labels, prices } = normalizeChartData(json.data);
        setChartLabels(labels);
        setChartPrices(prices);

        if (onPriceUpdate && json.data.length > 0) {
          const latest = json.data[json.data.length - 1];
          onPriceUpdate({ buy: parseFloat(latest.buy), sell: parseFloat(latest.price) });
        }
      } catch (err) {
        console.error("Error fetching chart data from backend:", err);
      }
    };

    fetchChartData();

    const scheduleRefresh = () => {
      const msToNextMinute = getMsToNextMinute();
      timeoutId = window.setTimeout(() => {
        fetchChartData();
        intervalId = window.setInterval(fetchChartData, REFRESH_INTERVAL_MS);
      }, msToNextMinute);
    };

    scheduleRefresh();

    return () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [onPriceUpdate]);

  const chartData = {
    labels: chartLabels,
    datasets: [{
      data: chartPrices,
      borderColor: "#eab308",
      backgroundColor: "rgba(234,179,8,0.15)",
      fill: true,
      tension: 0.2,
    }]
  };
  

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        type: "time",
        time: {
          unit: "minute",
          stepSize: STEP_MINUTES,
          displayFormats: { minute: "HH:mm" }
        },
        min: chartLabels.length ? chartLabels[0] : undefined,
        max: chartLabels.length ? chartLabels[chartLabels.length - 1] : undefined,
        ticks: {
          autoSkip: true,
          maxRotation: 0,
          maxTicksLimit: 12
        }
      }
    }
  };

  return (
    <div style={{ height: "300px", width: "100%", padding: "10px", boxSizing: "border-box" }}>
      <Line ref={chartRef} data={chartData} options={chartOptions} />
    </div>
  );
}
