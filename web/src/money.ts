const SYMBOL: Record<string, string> = { EUR: "€", GBP: "£", USD: "$" };

export function money(amount: number | null | undefined, currency: string): string {
  if (amount == null) return "—";
  const symbol = SYMBOL[currency];
  const digits = amount.toLocaleString("en-GB");
  return symbol ? `${symbol}${digits}` : `${digits} ${currency}`;
}
