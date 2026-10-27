"""
NammaSpace Collision Mesh Generator
Extracts 3D Gaussian centers from splat.ply and creates an optimized collision/navigation mesh
using Open3D Poisson Surface Reconstruction and Mesh Decimation.
"""

import os
import argparse
import numpy as np

try:
    import open3d as o3d
    from plyfile import PlyData
except ImportError:
    pass


def generate_collision_mesh(input_ply: str, output_path: str, depth: int = 8, target_triangles: int = 15000):
    print(f"[*] Reading Gaussian Splat from: {input_ply}")
    plydata = PlyData.read(input_ply)
    vertex = plydata["vertex"]

    x = np.array(vertex["x"])
    y = np.array(vertex["y"])
    z = np.array(vertex["z"])

    # Extract positions
    points = np.stack([x, y, z], axis=-1)
    print(f"[*] Loaded {len(points)} Gaussian centers.")

    # Filter by opacity if available
    if "opacity" in vertex:
        opacities = 1.0 / (1.0 + np.exp(-np.array(vertex["opacity"])))
        mask = opacities > 0.3
        points = points[mask]
        print(f"[*] Filtered low-opacity floaters: {len(points)} points retained.")

    # Create Open3D PointCloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # Statistical outlier removal
    print("[*] Removing outliers...")
    cl, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    pcd = pcd.select_by_index(ind)

    # Estimate normals
    print("[*] Estimating normals...")
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
    pcd.orient_normals_consistent_tangent_plane(10)

    # Poisson Surface Reconstruction
    print(f"[*] Running Poisson Reconstruction (depth={depth})...")
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)

    # Remove low density vertices (hallucinated geometry)
    densities = np.asarray(densities)
    density_threshold = np.quantile(densities, 0.05)
    vertices_to_remove = densities < density_threshold
    mesh.remove_vertices_by_mask(vertices_to_remove)

    # Simplify mesh for fast real-time collision
    print(f"[*] Simplifying mesh to ~{target_triangles} triangles...")
    mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_triangles)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()

    # Save output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    o3d.io.write_triangle_mesh(output_path, mesh)
    print(f"[+] Collision mesh saved successfully to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create physics collision mesh from 3DGS PLY")
    parser.add_argument("--input", type=str, required=True, help="Path to splat.ply")
    parser.add_argument("--output", type=str, required=True, help="Path to output collision mesh (.glb, .ply, or .obj)")
    parser.add_argument("--depth", type=int, default=8, help="Poisson depth octree (default: 8)")
    parser.add_argument("--triangles", type=int, default=15000, help="Target triangle count (default: 15000)")
    args = parser.parse_args()

    generate_collision_mesh(args.input, args.output, args.depth, args.triangles)
