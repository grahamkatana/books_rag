import { useState, useMemo } from "react";

/**
 * Client-side search + pagination over an already-fetched list. None of
 * the admin endpoints support server-side search/paging -- they return
 * everything in one response -- so this filters and slices in the
 * browser instead. Fine for the data volumes an admin tool like this
 * deals with; if a deployment's user/book/chat counts ever get large
 * enough for that to matter, the right fix is adding real query params
 * to the backend, not a smarter client-side hook.
 */
export function useSearchAndPaginate(items, { searchFields, pageSize = 10 }) {
  const [query, setQueryRaw] = useState("");
  const [page, setPageRaw] = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) =>
      searchFields.some((field) => {
        const value = item[field];
        return value != null && String(value).toLowerCase().includes(q);
      })
    );
  }, [items, query, searchFields]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  // Clamp rather than reset elsewhere -- if the list shrinks (e.g. a
  // delete) while on the last page, this just pulls back to the new
  // last page instead of showing an empty one.
  const currentPage = Math.min(page, totalPages);

  const pageItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  // Changing the search query always jumps back to page 1 -- otherwise
  // a narrower result set could leave you stranded on a page that no
  // longer has anything on it.
  const setQuery = (value) => {
    setQueryRaw(value);
    setPageRaw(1);
  };

  return {
    query,
    setQuery,
    page: currentPage,
    setPage: setPageRaw,
    totalPages,
    totalCount: filtered.length,
    pageSize,
    items: pageItems,
  };
}
