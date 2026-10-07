// SPDX-License-Identifier: Apache-2.0
import { Box3, BufferGeometry, Float32BufferAttribute, Line3, Mesh, Object3D, Vector3 } from 'three';
import { MeshBVH } from 'three-mesh-bvh';
import { PLAYER_HALF_HEIGHT, PLAYER_RADIUS } from './world-data';

/** World-space triangles preserve capsule size under nonuniform model scaling. */
export class MeshCollision {
  private readonly geometry = new BufferGeometry();
  private readonly tree: MeshBVH;
  private readonly bounds = new Box3();
  private readonly capsuleBounds = new Box3();
  private readonly segment = new Line3();
  private readonly onTriangle = new Vector3();
  private readonly onCapsule = new Vector3();
  private readonly correction = new Vector3();
  private disposed = false;
  private readonly supportCenter = new Vector3();
  private readonly supportPoint = new Vector3();
  private readonly supportDelta = new Vector3();
  private readonly supportNormal = new Vector3();
  private readonly supportBounds = new Box3();

  constructor(root: Object3D) {
    root.updateWorldMatrix(true, true);
    const positions: number[] = [];
    root.traverse(object => {
      if (!(object instanceof Mesh) || object.userData.browserStaticBatch) return;
      const geometry = object.geometry;
      const attribute = geometry.getAttribute('position');
      if (!attribute) return;
      const point = new Vector3();
      const count = geometry.index?.count ?? attribute.count;
      for (let index = 0; index < count; index++) {
        point.fromBufferAttribute(attribute, geometry.index ? geometry.index.getX(index) : index).applyMatrix4(object.matrixWorld);
        positions.push(point.x, point.y, point.z);
      }
    });
    this.geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
    this.tree = new MeshBVH(this.geometry, { targetLeafSize: 12 });
    this.tree.getBoundingBox(this.bounds);
  }

  /** Read-only bottom-sphere support on genuine current world-space triangles.
   * A small tolerance recognizes an exactly touching capsule without moving it.
   * Contact direction matches resolve's grounding normal; triangle winding does
   * not create a floor, and no oriented model bounds qualify as support. */
  supports(position: Vector3, tolerance = 0.02): boolean {
    if (!Number.isFinite(tolerance) || tolerance < 0 || tolerance > 0.05) throw Error('Invalid capsule support tolerance');
    if (this.disposed || !Number.isFinite(position.x) || !Number.isFinite(position.y) || !Number.isFinite(position.z)) return false;
    this.supportCenter.set(position.x, position.y - PLAYER_HALF_HEIGHT + PLAYER_RADIUS, position.z);
    const maximum = PLAYER_RADIUS + tolerance;
    this.supportBounds.makeEmpty().expandByPoint(this.supportCenter).expandByScalar(maximum);
    if (!this.supportBounds.intersectsBox(this.bounds)) return false;
    let supported = false;
    this.tree.shapecast({
      intersectsBounds: bounds => bounds.intersectsBox(this.supportBounds),
      intersectsTriangle: triangle => {
        // An internal wall-triangle edge can produce an upward nearest-point
        // direction. Require an actually walkable plane as well as contact.
        triangle.getNormal(this.supportNormal);
        if (Math.abs(this.supportNormal.y) <= 0.5) return false;
        triangle.closestPointToPoint(this.supportCenter, this.supportPoint);
        this.supportDelta.subVectors(this.supportCenter, this.supportPoint);
        const distance = this.supportDelta.length();
        if (distance < 1e-8 || distance > maximum) return false;
        if (this.supportDelta.y / distance <= 0.5) return false;
        supported = true;
        return true;
      },
    });
    return supported;
  }

  /** Returns the contact normal and modifies the position only on actual triangles. */
  resolve(position: Vector3): Vector3 | undefined {
    if (this.disposed) return;
    const halfSegment = PLAYER_HALF_HEIGHT - PLAYER_RADIUS;
    this.segment.start.copy(position).add(new Vector3(0, -halfSegment, 0));
    this.segment.end.copy(position).add(new Vector3(0, halfSegment, 0));
    this.capsuleBounds.makeEmpty().expandByPoint(this.segment.start).expandByPoint(this.segment.end).expandByScalar(PLAYER_RADIUS);
    if (!this.capsuleBounds.intersectsBox(this.bounds)) return;
    this.correction.set(0, 0, 0);
    this.tree.shapecast({
      intersectsBounds: bounds => bounds.intersectsBox(this.capsuleBounds),
      intersectsTriangle: triangle => {
        const distance = triangle.closestPointToSegment(this.segment, this.onTriangle, this.onCapsule);
        if (distance >= PLAYER_RADIUS) return false;
        const normal = this.onCapsule.sub(this.onTriangle);
        let depth = PLAYER_RADIUS - distance;
        if (distance > 1e-8) normal.multiplyScalar(1 / distance);
        else {
          triangle.getNormal(normal);
          if (normal.dot(position.clone().sub(triangle.a)) < 0) normal.negate();
          // A capsule segment can cross a floor after spawn or while stepping.
          // Move the entire segment to its original side, rather than one radius
          // per frame; otherwise it can remain embedded in a walkable surface.
          depth = PLAYER_RADIUS - Math.min(normal.dot(this.segment.start.clone().sub(triangle.a)), normal.dot(this.segment.end.clone().sub(triangle.a)));
        }
        normal.multiplyScalar(depth + 0.00001);
        this.segment.start.add(normal); this.segment.end.add(normal); this.correction.add(normal);
        return false;
      },
    });
    if (this.correction.lengthSq() < 1e-12) return;
    position.add(this.correction);
    return this.correction.normalize().clone();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.geometry.dispose();
  }
}
