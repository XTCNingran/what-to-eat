import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

export const sb = createClient(
  'https://anvfuiuwatibbkfbuuvj.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFudmZ1aXV3YXRpYmJrZmJ1dXZqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyMjQyNzMsImV4cCI6MjA5MzgwMDI3M30.Ut2PJ3VzXD8QVpKTWfVQF8KuVvdnzU4Ogt-TyMEix1Q'
);
