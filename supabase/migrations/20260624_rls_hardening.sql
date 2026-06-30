-- RLS hardening (audit remediation).
--
-- Several "Service role can/manages X" policies were declared
--   FOR ALL USING (true) WITH CHECK (true)
-- with NO `TO service_role` qualifier. Without a TO clause a policy applies to
-- the `public` role (anon + authenticated), and because PERMISSIVE policies are
-- OR-combined, each one *overrode* its adjacent owner-scoped policy — letting any
-- logged-in PostgREST (anon-key) client read/write every tenant's rows.
--
-- The backend connects as the service_role key, which BYPASSES RLS, so these
-- policies were never needed for the backend; re-scoping them `TO service_role`
-- keeps backend behaviour identical while removing the public hole.
--
-- Also fixes the org_members "Admins can manage members" policy, whose USING
-- clause subqueried org_members itself (infinite recursion, 42P17) and had no
-- WITH CHECK, via a SECURITY DEFINER helper.

-- token_usage --------------------------------------------------------------
DROP POLICY IF EXISTS "Service role can manage token usage" ON token_usage;
CREATE POLICY "Service role can manage token usage"
  ON token_usage FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- agent_heartbeats ---------------------------------------------------------
DROP POLICY IF EXISTS "Service role can manage heartbeats" ON agent_heartbeats;
CREATE POLICY "Service role can manage heartbeats"
  ON agent_heartbeats FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- task_group_members -------------------------------------------------------
DROP POLICY IF EXISTS "Service role manages members" ON task_group_members;
CREATE POLICY "Service role manages members"
  ON task_group_members FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- agent_messages -----------------------------------------------------------
DROP POLICY IF EXISTS "Service role manages messages" ON agent_messages;
CREATE POLICY "Service role manages messages"
  ON agent_messages FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- computer_use_audit_log ---------------------------------------------------
DROP POLICY IF EXISTS "Service role can insert audit logs" ON computer_use_audit_log;
CREATE POLICY "Service role can insert audit logs"
  ON computer_use_audit_log FOR INSERT TO service_role
  WITH CHECK (true);

-- org_members: break RLS recursion (42P17) via SECURITY DEFINER helper -----
CREATE OR REPLACE FUNCTION is_org_member_admin(p_org_id uuid)
  RETURNS boolean
  LANGUAGE sql
  SECURITY DEFINER
  STABLE
  SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM organizations
      WHERE id = p_org_id AND owner_id = auth.uid()
    UNION ALL
    SELECT 1 FROM org_members
      WHERE org_id = p_org_id AND user_id = auth.uid() AND role IN ('admin', 'owner')
  );
$$;

DROP POLICY IF EXISTS "Admins can manage members" ON org_members;
CREATE POLICY "Admins can manage members"
  ON org_members FOR ALL
  USING (is_org_member_admin(org_id))
  WITH CHECK (is_org_member_admin(org_id));
