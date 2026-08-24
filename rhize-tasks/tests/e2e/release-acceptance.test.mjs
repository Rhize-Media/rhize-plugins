import assert from 'node:assert/strict';
import test from 'node:test';

import {runFakeReleaseAcceptance} from './support/release-fixture.mjs';

test('Tom-Mac release workflow stays bounded across setup, planning, recovery, and uninstall', async t => {
  const result = await runFakeReleaseAcceptance(t);
  assert.deepEqual(result, {
    stagesCompleted: 7,
    firstPlanApproved: true,
    noDuplicateOwnedItems: true,
    carryoverPrompted: true,
    delegationMergedExactly: true,
    reconciliationPrompted: true,
    pauseRestartCatchUpSafe: true,
    revocationFailsClosed: true,
    uninstallCleanupVerified: true,
    outsideRecordsUnchanged: true,
  });
});
