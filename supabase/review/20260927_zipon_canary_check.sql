-- Read-only canary verification AFTER separately authorized import. No import here.
BEGIN READ ONLY;
SELECT p.project_id,p.project_name,p.project_type,p.sigungu,p.address,p.official_authority,p.external_id,
p.stage,p.stage_raw,p.status,p.validation_status,p.revision,
(SELECT count(*) FROM public.development_project_sources s WHERE s.project_id=p.project_id) AS source_count,
(SELECT count(*) FROM public.development_updates u WHERE u.project_id=p.project_id) AS history_count
FROM public.development_projects p WHERE p.project_id IN ('02b9c94c-8b6c-5297-affa-1e827181afb0'::uuid,'0922ac26-1436-5158-853d-49d3c5aed7fb'::uuid,'429dc953-a406-56ff-871d-0ced658be69f'::uuid,'070e2349-2569-5652-8d56-bc8080b20304'::uuid,'0cfa354d-f9ac-5516-aa2a-1f6767c0aa98'::uuid,'8ab19fc2-5f02-54a8-9568-6a3ef0218ec4'::uuid,'0164b2b0-1b21-51e3-8b8d-f97bda852a18'::uuid,'dde3dfc6-ca79-5226-b3c6-a16a9872043c'::uuid) ORDER BY p.sigungu,p.project_type;
SELECT s.project_id,s.source_url,s.is_official,s.validation_status,s.content_hash
FROM public.development_project_sources s WHERE s.project_id IN ('02b9c94c-8b6c-5297-affa-1e827181afb0'::uuid,'0922ac26-1436-5158-853d-49d3c5aed7fb'::uuid,'429dc953-a406-56ff-871d-0ced658be69f'::uuid,'070e2349-2569-5652-8d56-bc8080b20304'::uuid,'0cfa354d-f9ac-5516-aa2a-1f6767c0aa98'::uuid,'8ab19fc2-5f02-54a8-9568-6a3ef0218ec4'::uuid,'0164b2b0-1b21-51e3-8b8d-f97bda852a18'::uuid,'dde3dfc6-ca79-5226-b3c6-a16a9872043c'::uuid);
SELECT p.official_authority,p.external_id,count(*) FROM public.development_projects p
WHERE p.external_id IS NOT NULL AND p.project_id IN ('02b9c94c-8b6c-5297-affa-1e827181afb0'::uuid,'0922ac26-1436-5158-853d-49d3c5aed7fb'::uuid,'429dc953-a406-56ff-871d-0ced658be69f'::uuid,'070e2349-2569-5652-8d56-bc8080b20304'::uuid,'0cfa354d-f9ac-5516-aa2a-1f6767c0aa98'::uuid,'8ab19fc2-5f02-54a8-9568-6a3ef0218ec4'::uuid,'0164b2b0-1b21-51e3-8b8d-f97bda852a18'::uuid,'dde3dfc6-ca79-5226-b3c6-a16a9872043c'::uuid) GROUP BY 1,2 HAVING count(*)>1;
ROLLBACK;
