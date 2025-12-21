"use client";

import React from "react";

/**
 * 颜色块组件，用于显示颜色块和颜色码
 * @param {Object} props - 组件属性
 * @param {string} props.colorHex - 颜色码，格式如 #FFFFFF 或 FFFFFFFF
 * @param {string} props.colorName - 颜色名称
 * @param {number} props.size - 颜色块大小，默认为 24
 * @param {boolean} props.showHex - 是否显示颜色码文本，默认为 false
 * @returns {React.Element} 颜色块组件
 */
export function ColorBlock({ colorHex, colorName, size = 24, showHex = false }) {
  // 显示颜色块，假设后端已经标准化了颜色码格式
  const normalizedColor = colorHex || "#CCCCCC"; // 如果没有颜色码，使用默认灰色
  
  return (
    <div className="flex items-center gap-2">
      <div
        className="rounded border border-gray-300"
        style={{
          backgroundColor: normalizedColor,
          width: `${size}px`,
          height: `${size}px`,
        }}
        title={`${colorName || "未知颜色"} (${normalizedColor})`}
      />
      {showHex && (
        <span className="text-xs text-muted-foreground font-mono">
          {normalizedColor}
        </span>
      )}
    </div>
  );
}
