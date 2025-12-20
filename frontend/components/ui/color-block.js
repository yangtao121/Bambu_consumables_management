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
  // 处理颜色码格式，确保以 # 开头且只包含6位十六进制
  const getNormalizedColor = (hex) => {
    if (!hex) return "#CCCCCC"; // 默认灰色
    
    // 移除 # 前缀
    let color = hex.startsWith('#') ? hex.substring(1) : hex;
    
    // 如果是8位（FFFFFFFF），去掉前两位或后两位的Alpha通道
    if (color.length === 8) {
      color = color.substring(0, 6);
    }
    
    // 确保6位长度
    if (color.length !== 6) {
      return "#CCCCCC"; // 无效颜色返回默认灰色
    }
    
    return `#${color}`;
  };
  
  const normalizedColor = getNormalizedColor(colorHex);
  
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
