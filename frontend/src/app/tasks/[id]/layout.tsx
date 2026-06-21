export function generateStaticParams() {
  return [{ id: "blank" }];
}

export default function TaskLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
