// api/services/beads.ts (new function added at end of file)

export interface ClaimResult {
  success: boolean
  reason?: 'not_found' | 'unavailable'
  beadId?: string
  assignee?: string
}

export async function claimBead(
  beadId: string,
  workerId: string,
): Promise<ClaimResult> {
  const bead = await db.beads.findOne({ id: beadId })
  if (!bead) {
    return { success: false, reason: 'not_found' }
  }
  if (bead.status !== 'ready' || bead.assignee !== null) {
    return { success: false, reason: 'unavailable' }
  }

  // Bead is available, claim it
  await db.beads.update(
    { id: beadId },
    {
      status: 'in_progress',
      assignee: workerId,
      claimedAt: new Date(),
    },
  )

  return { success: true, beadId, assignee: workerId }
}
