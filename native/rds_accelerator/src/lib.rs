//! Optional ordered closure of declared labels, never a scientific proof kernel.
const NO_EDGE: u32 = u32::MAX;

#[no_mangle]
pub extern "C" fn rds_accelerator_smoke() -> i32 { 42 }
#[no_mangle]
pub extern "C" fn rds_accelerator_abi_version() -> u32 { 2 }

/// Returns 0 on success, -1 on malformed input. No partial output on rejection.
///
/// # Safety
/// Caller owns valid, non-overlapping buffers of declared lengths. Zero-length
/// buffers may be null. Invalid non-null pointers cannot be checked by this ABI.
#[no_mangle]
pub unsafe extern "C" fn rds_hypergraph_closure_v2(
    num_nodes: u32, contradicted: *const u8,
    initial: *const u32, initial_len: usize,
    flat: *const u32, flat_len: usize,
    out: *mut u8, witnesses: *mut u32,
    conflicts: *mut u8, edge_count: usize,
) -> i32 {
    let n = num_nodes as usize;
    if n > 4096 || edge_count > 16384 || initial_len > n ||
       flat_len > edge_count.saturating_mul(n + 2) ||
       (n > 0 && (contradicted.is_null() || out.is_null() || witnesses.is_null())) ||
       (initial_len > 0 && initial.is_null()) || (flat_len > 0 && flat.is_null()) ||
       (edge_count > 0 && conflicts.is_null()) { return -1; }
    let blocked = if n == 0 { &[] } else { std::slice::from_raw_parts(contradicted, n) };
    let seeds = if initial_len == 0 { &[] } else { std::slice::from_raw_parts(initial, initial_len) };
    let input = if flat_len == 0 { &[] } else { std::slice::from_raw_parts(flat, flat_len) };
    if blocked.iter().any(|&x| x > 1) ||
       seeds.iter().any(|&x| x as usize >= n || blocked[x as usize] != 0) { return -1; }
    let mut edges = Vec::new();
    let mut pos = 0;
    while pos < input.len() {
        if input.len() - pos < 2 { return -1; }
        let head = input[pos] as usize;
        let len = input[pos + 1] as usize;
        pos += 2;
        if head >= n || len > n || len > input.len() - pos { return -1; }
        let tails = &input[pos..pos + len];
        if tails.iter().any(|&p| p as usize >= n) { return -1; }
        edges.push((head, tails));
        pos += len;
    }
    if edges.len() != edge_count { return -1; }
    let mut closed = vec![0u8; n];
    let mut proof = vec![NO_EDGE; n];
    let mut rejected = vec![0u8; edge_count];
    for &seed in seeds { closed[seed as usize] = 1; }
    loop {
        let mut changed = false;
        for (i, (head, tails)) in edges.iter().enumerate() {
            if !tails.iter().all(|&p| closed[p as usize] != 0) { continue; }
            if blocked[*head] != 0 { rejected[i] = 1; }
            else if closed[*head] == 0 {
                closed[*head] = 1;
                proof[*head] = i as u32;
                changed = true;
            }
        }
        if !changed { break; }
    }
    if n > 0 {
        std::slice::from_raw_parts_mut(out, n).copy_from_slice(&closed);
        std::slice::from_raw_parts_mut(witnesses, n).copy_from_slice(&proof);
    }
    if edge_count > 0 {
        std::slice::from_raw_parts_mut(conflicts, edge_count).copy_from_slice(&rejected);
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn contradiction_cannot_support_descendant() {
        let blocked = [0, 1, 0];
        let flat = [1, 1, 0, 2, 1, 1];
        let mut out = [0; 3]; let mut witnesses = [NO_EDGE; 3]; let mut conflicts = [0; 2];
        let result = unsafe { rds_hypergraph_closure_v2(3, blocked.as_ptr(), [0].as_ptr(), 1,
            flat.as_ptr(), flat.len(), out.as_mut_ptr(), witnesses.as_mut_ptr(), conflicts.as_mut_ptr(), 2) };
        assert_eq!(result, 0); assert_eq!(out, [1, 0, 0]); assert_eq!(conflicts, [1, 0]);
        assert_eq!(witnesses, [NO_EDGE; 3]);
    }
    #[test]
    fn malformed_and_empty_inputs() {
        let mut out = [9]; let mut witnesses = [NO_EDGE]; let mut conflicts = [9];
        let result = unsafe { rds_hypergraph_closure_v2(1, [0].as_ptr(), std::ptr::null(), 0,
            [0, 2, 0].as_ptr(), 3, out.as_mut_ptr(), witnesses.as_mut_ptr(), conflicts.as_mut_ptr(), 1) };
        assert_eq!(result, -1); assert_eq!(out, [9]); assert_eq!(conflicts, [9]);
        assert_eq!(unsafe { rds_hypergraph_closure_v2(0, std::ptr::null(), std::ptr::null(), 0,
            std::ptr::null(), 0, std::ptr::null_mut(), std::ptr::null_mut(), std::ptr::null_mut(), 0) }, 0);
    }
    #[test]
    fn seed_range_and_ordered_witnesses() {
        let mut out = [0; 3]; let mut witnesses = [NO_EDGE; 3]; let mut conflicts = [0; 3];
        let flat = [2, 1, 1, 1, 1, 0, 2, 1, 0];
        let result = unsafe { rds_hypergraph_closure_v2(3, [0,0,0].as_ptr(), [0].as_ptr(), 1,
            flat.as_ptr(), flat.len(), out.as_mut_ptr(), witnesses.as_mut_ptr(), conflicts.as_mut_ptr(), 3) };
        assert_eq!(result, 0); assert_eq!(out, [1,1,1]); assert_eq!(witnesses, [NO_EDGE,1,2]);
        assert_eq!(unsafe { rds_hypergraph_closure_v2(3, [0,0,0].as_ptr(), [3].as_ptr(), 1,
            flat.as_ptr(), flat.len(), out.as_mut_ptr(), witnesses.as_mut_ptr(), conflicts.as_mut_ptr(), 3) }, -1);
    }
}
