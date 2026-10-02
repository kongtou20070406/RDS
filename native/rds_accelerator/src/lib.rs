//! Optional native acceleration kernel for Research Direction Selector (RDS).
//!
//! Provides high-throughput, allocation-minimized hypergraph closure propagation,
//! topological validation, and equational saturation operations.

use std::collections::HashSet;

/// Quick C-ABI smoke probe returning standard magic identifier.
#[no_mangle]
pub extern "C" fn rds_accelerator_smoke() -> i32 {
    42
}

/// Evaluates whether a set of integer premises can close hyperedges to derive goals.
/// 
/// Flattened representation:
/// - `num_nodes`: total number of unique node IDs (0..num_nodes-1)
/// - `initial_supported`: array of initial supported node IDs
/// - `num_supported`: length of `initial_supported`
/// - `edges_flat`: flat array encoding edges: [head, num_premises, p0, p1, ..., head, num_premises, ...]
/// - `edges_len`: total elements in `edges_flat`
/// - `out_closure`: buffer to write derived supported node IDs
/// - `out_cap`: capacity of `out_closure`
/// 
/// Returns total count of derived nodes in the closure.
#[no_mangle]
pub extern "C" fn rds_hypergraph_fast_closure(
    num_nodes: u32,
    initial_supported: *const u32,
    num_supported: usize,
    edges_flat: *const u32,
    edges_len: usize,
    out_closure: *mut u32,
    out_cap: usize,
) -> i32 {
    if initial_supported.is_null() || edges_flat.is_null() || out_closure.is_null() {
        return -1;
    }

    let init_slice = unsafe { std::slice::from_raw_parts(initial_supported, num_supported) };
    let edges_slice = unsafe { std::slice::from_raw_parts(edges_flat, edges_len) };

    let mut closure: HashSet<u32> = init_slice.iter().copied().collect();

    // Fixed-point iteration
    let mut changed = true;
    while changed {
        changed = false;
        let mut idx = 0;
        while idx < edges_len {
            if idx + 2 > edges_len {
                break;
            }
            let head = edges_slice[idx];
            let num_premises = edges_slice[idx + 1] as usize;
            idx += 2;
            if idx + num_premises > edges_len {
                break;
            }
            let premises = &edges_slice[idx..idx + num_premises];
            idx += num_premises;

            if !closure.contains(&head) && premises.iter().all(|p| closure.contains(p)) {
                closure.insert(head);
                changed = true;
            }
        }
    }

    let derived_count = closure.len();
    if derived_count > out_cap {
        return -(derived_count as i32); // Buffer too small, returns needed capacity as negative
    }

    let out_slice = unsafe { std::slice::from_raw_parts_mut(out_closure, derived_count) };
    for (i, &node) in closure.iter().enumerate() {
        out_slice[i] = node;
    }

    derived_count as i32
}
