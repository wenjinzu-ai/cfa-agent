"""CFA-Agent 数据分析工具"""
from __future__ import annotations

import json
import re
from typing import Any

from src.tools.base import BaseTool


class DataAnalysis(BaseTool):
    """数据分析工具

    提供基础统计分析、相关性分析、分布分析等功能
    """

    name: str = "data_analysis"
    description: str = (
        "Analyze data, generate statistics, calculate correlations, and identify patterns"
    )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "JSON string of data to analyze (list of numbers or objects)",
                },
                "operation": {
                    "type": "string",
                    "description": "Analysis operation: describe, correlation, distribution, outliers, summary",
                    "enum": ["describe", "correlation", "distribution", "outliers", "summary"],
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to analyze (for object data)",
                },
            },
            "required": ["data", "operation"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        data_str = kwargs.get("data", "[]")
        operation = kwargs.get("operation", "describe")
        columns = kwargs.get("columns", [])

        try:
            import json
            data = json.loads(data_str) if isinstance(data_str, str) else data_str
        except (json.JSONDecodeError, TypeError):
            return {"error": "Invalid JSON data", "status": "error"}

        if not data:
            return {"error": "Empty data", "status": "error"}

        try:
            if operation == "describe":
                return self._describe(data, columns)
            elif operation == "correlation":
                return self._correlation(data, columns)
            elif operation == "distribution":
                return self._distribution(data, columns)
            elif operation == "outliers":
                return self._outliers(data, columns)
            elif operation == "summary":
                return self._summary(data, columns)
            else:
                return {"error": f"Unknown operation: {operation}", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def _extract_numeric(self, data: list, columns: list[str]) -> list[float]:
        values = []
        for item in data:
            if isinstance(item, (int, float)):
                values.append(float(item))
            elif isinstance(item, dict) and columns:
                for col in columns:
                    if col in item and isinstance(item[col], (int, float)):
                        values.append(float(item[col]))
        return values

    def _describe(self, data: list, columns: list[str]) -> dict[str, Any]:
        values = self._extract_numeric(data, columns)
        if not values:
            return {"operation": "describe", "error": "No numeric data found", "status": "error"}

        n = len(values)
        mean = sum(values) / n
        sorted_vals = sorted(values)
        median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0

        return {
            "operation": "describe",
            "count": n,
            "mean": round(mean, 4),
            "median": round(median, 4),
            "std": round(variance ** 0.5, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "range": round(max(values) - min(values), 4),
            "status": "success",
        }

    def _correlation(self, data: list, columns: list[str]) -> dict[str, Any]:
        if not columns or len(columns) < 2:
            return {"operation": "correlation", "error": "Need at least 2 columns", "status": "error"}

        col_values = {}
        for col in columns:
            col_values[col] = []
            for item in data:
                if isinstance(item, dict) and col in item and isinstance(item[col], (int, float)):
                    col_values[col].append(float(item[col]))

        correlations = {}
        for i, col1 in enumerate(columns):
            for col2 in columns[i + 1:]:
                vals1 = col_values[col1]
                vals2 = col_values[col2]
                if len(vals1) == len(vals2) and len(vals1) > 1:
                    n = len(vals1)
                    mean1 = sum(vals1) / n
                    mean2 = sum(vals2) / n
                    cov = sum((vals1[j] - mean1) * (vals2[j] - mean2) for j in range(n))
                    std1 = (sum((v - mean1) ** 2 for v in vals1) / (n - 1)) ** 0.5
                    std2 = (sum((v - mean2) ** 2 for v in vals2) / (n - 1)) ** 0.5
                    if std1 > 0 and std2 > 0:
                        correlations[f"{col1} vs {col2}"] = round(cov / (n * std1 * std2), 4)

        return {"operation": "correlation", "correlations": correlations, "status": "success"}

    def _distribution(self, data: list, columns: list[str]) -> dict[str, Any]:
        values = self._extract_numeric(data, columns)
        if not values:
            return {"operation": "distribution", "error": "No numeric data found", "status": "error"}

        n = len(values)
        sorted_vals = sorted(values)
        buckets = 10
        bucket_size = (max(values) - min(values)) / buckets if max(values) != min(values) else 1
        distribution = []
        for i in range(buckets):
            low = min(values) + i * bucket_size
            high = low + bucket_size
            count = sum(1 for v in values if low <= v < high)
            distribution.append({"range": f"[{round(low, 2)}, {round(high, 2)})", "count": count})

        return {"operation": "distribution", "distribution": distribution, "total": n, "status": "success"}

    def _outliers(self, data: list, columns: list[str]) -> dict[str, Any]:
        values = self._extract_numeric(data, columns)
        if not values:
            return {"operation": "outliers", "error": "No numeric data found", "status": "error"}

        sorted_vals = sorted(values)
        q1 = sorted_vals[len(sorted_vals) // 4]
        q3 = sorted_vals[3 * len(sorted_vals) // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = [v for v in values if v < lower or v > upper]

        return {
            "operation": "outliers",
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
            "lower_bound": round(lower, 4),
            "upper_bound": round(upper, 4),
            "outliers": [round(v, 4) for v in outliers],
            "count": len(outliers),
            "status": "success",
        }

    def _summary(self, data: list, columns: list[str]) -> dict[str, Any]:
        desc = self._describe(data, columns)
        if desc.get("status") == "error":
            return desc
        return {"operation": "summary", **desc, "status": "success"}