import { redirect } from "next/navigation";

export default function Page() {
  // 本系统已切换为“库存（material+color+brand）”模型，spools 页面废弃。
  redirect("/stocks");
}
