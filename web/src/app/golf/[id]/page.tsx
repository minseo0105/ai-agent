import GolfDetail from "@/components/golf/GolfDetail";

export default async function GolfClubPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let clubId = id;
  try {
    clubId = decodeURIComponent(id);
  } catch {}
  return <GolfDetail id={clubId} />;
}
