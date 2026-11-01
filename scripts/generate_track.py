"""Regenerate the static track asset; uses only the Python standard library."""

import math
from pathlib import Path

# Rounded, closed circuit with a central hairpin. All dimensions are meters.
vertices = [(0, 0), (16, 0), (16, 12), (10, 12), (10, 5), (6, 5), (6, 12), (0, 12)]
radius, half_width = 1.8, 1.2
corners = []
for i, (x, y) in enumerate(vertices):
    px, py = vertices[i - 1]
    nx, ny = vertices[(i + 1) % len(vertices)]
    length_in, length_out = math.hypot(x-px, y-py), math.hypot(nx-x, ny-y)
    dx, dy = (x-px)/length_in, (y-py)/length_in
    ex, ey = (nx-x)/length_out, (ny-y)/length_out
    turn = dx*ey-dy*ex
    cx, cy = x-radius*dx+radius*ex, y-radius*dy+radius*ey
    angle = math.atan2(-ey, -ex)
    arc = []
    for j in range(25):
        a = angle + turn*math.pi/2*j/24
        arc.append((cx+radius*math.cos(a), cy+radius*math.sin(a), -turn*math.sin(a), turn*math.cos(a)))
    corners.append(arc)
path = []
for i, arc in enumerate(corners):
    path.extend(arc)
    x, y, dx, dy = arc[-1]
    nx, ny, _, _ = corners[(i+1) % len(corners)][0]
    length = math.hypot(nx-x, ny-y)
    for j in range(1, math.ceil(length)):
        f = j/math.ceil(length)
        path.append((x+(nx-x)*f, y+(ny-y)*f, dx, dy))
left = [(x-dy*half_width, y+dx*half_width) for x,y,dx,dy in path]
right = [(x+dy*half_width, y-dx*half_width) for x,y,dx,dy in path]

def vec(values):
    return '(' + ', '.join(f'{v:.5f}' for v in values) + ')'

lines = ['#usda 1.0', '(', '    defaultPrim = "Track"', '    metersPerUnit = 1', '    upAxis = "Z"', ')',
         '# Static 20 x 16 m track. Lane: 2.4 m; barriers: 0.8 m tall, 0.22 m thick.', 'def Xform "Track"', '{']
for name, color in [('Asphalt',(.065,.075,.08)),('Concrete',(.44,.46,.45)),('Red',(.65,.025,.04)),('White',(.9,.9,.85))]:
    lines.extend([f'    def Material "{name}"', '    {',
                  f'        token outputs:surface.connect = </Track/{name}/Shader.outputs:surface>',
                  '        def Shader "Shader"', '        {', '            uniform token info:id = "UsdPreviewSurface"',
                  f'            color3f inputs:diffuseColor = {vec(color)}', '            float inputs:roughness = 0.9',
                  '            token outputs:surface', '        }', '    }'])

def box(name, position, scale, material, angle=0):
    lines.extend([f'    def Cube "{name}" (', '        prepend apiSchemas = ["PhysicsCollisionAPI", "MaterialBindingAPI"]',
                  '    )', '    {', '        double size = 1', f'        rel material:binding = </Track/{material}>',
                  f'        double3 xformOp:translate = {vec(position)}', f'        float xformOp:rotateZ = {angle:.5f}',
                  f'        double3 xformOp:scale = {vec(scale)}',
                  '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateZ", "xformOp:scale"]', '    }'])

def mesh(name, points, faces, material):
    lines.extend([f'    def Mesh "{name}" (', '        prepend apiSchemas = ["MaterialBindingAPI"]', '    )', '    {',
                  '        uniform token subdivisionScheme = "none"', '        uniform bool doubleSided = true',
                  f'        rel material:binding = </Track/{material}>',
                  '        point3f[] points = [' + ', '.join(vec(p) for p in points) + ']',
                  '        int[] faceVertexCounts = [' + ', '.join('4' for _ in faces) + ']',
                  '        int[] faceVertexIndices = [' + ', '.join(str(v) for face in faces for v in face) + ']', '    }'])

box('Foundation', (8,6,-.1), (20,16,.2), 'Concrete')
points = [(x,y,.002) for a,b in zip(left,right) for x,y in (a,b)]
faces = [(2*i,2*i+1,2*((i+1)%len(path))+1,2*((i+1)%len(path))) for i in range(len(path))]
mesh('Road', points, faces, 'Asphalt')
# Each wall is one closed, shared-vertex mesh. Mitered joins avoid overlapping
# faces; the same triangle mesh supplies static collision around the whole loop.
for side, boundary in [('Inner', left), ('Outer', right)]:
    points, normals, faces = [], [], []
    colors = {'Red': [], 'White': []}
    side_normals = []
    for i, (x, y) in enumerate(boundary):
        px, py = boundary[i-1]
        nx, ny = boundary[(i+1) % len(boundary)]
        before, after = math.hypot(x-px, y-py), math.hypot(nx-x, ny-y)
        ax, ay = -(y-py)/before, (x-px)/before
        bx, by = -(ny-y)/after, (nx-x)/after
        # Intersect the offset edge lines to meet exactly at every join.
        scale = .11 / (1 + ax*bx + ay*by)
        ox, oy = (ax+bx)*scale, (ay+by)*scale
        length = math.hypot(ox, oy)
        side_normals.append((ox/length, oy/length, 0))
        points.extend([(x+ox,y+oy,0), (x-ox,y-oy,0),
                       (x+ox,y+oy,.8), (x-ox,y-oy,.8)])
    distance = 0
    for i, (x, y) in enumerate(boundary):
        j = (i+1) % len(boundary)
        a, b = 4*i, 4*j
        faces.extend([(a,a+2,b+2,b), (a+1,b+1,b+3,a+3),
                      (a+2,a+3,b+3,b+2), (a,b,b+1,a+1)])
        ni, nj = side_normals[i], side_normals[j]
        normals.extend([ni, ni, nj, nj])
        normals.extend([tuple(-v for v in n) for n in (ni,nj,nj,ni)])
        normals.extend([(0,0,1)]*4 + [(0,0,-1)]*4)
        length = math.dist(boundary[i], boundary[j])
        color = 'Red' if int((distance+length/2)/.85) % 2 == 0 else 'White'
        colors[color].extend(range(4*i, 4*i+4))
        distance += length
    lines.extend([f'    def Mesh "{side}Barrier" (',
                  '        prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI", "MaterialBindingAPI"]',
                  '    )', '    {',
                  '        uniform token subdivisionScheme = "none"',
                  '        token physics:approximation = "none"',
                  '        uniform token subsetFamily:materialBind:familyType = "partition"',
                  '        point3f[] points = [' + ', '.join(vec(p) for p in points) + ']',
                  '        int[] faceVertexCounts = [' + ', '.join('4' for _ in faces) + ']',
                  '        int[] faceVertexIndices = [' + ', '.join(str(v) for face in faces for v in face) + ']',
                  '        normal3f[] normals = [' + ', '.join(vec(n) for n in normals) + '] (',
                  '            interpolation = "faceVarying"', '        )'])
    for color, indices in colors.items():
        lines.extend([f'        def GeomSubset "{color}" (',
                      '            prepend apiSchemas = ["MaterialBindingAPI"]', '        )', '        {',
                      '            uniform token elementType = "face"',
                      '            uniform token familyName = "materialBind"',
                      '            int[] indices = [' + ', '.join(map(str, indices)) + ']',
                      f'            rel material:binding = </Track/{color}>', '        }'])
    lines.append('    }')
# Painted start/finish checkerboard: visual only, no extra collision surfaces.
for parity, material in [(0,'White'),(1,'Asphalt')]:
    points, faces = [], []
    for row in range(2):
        for column in range(8):
            if (row+column)%2 != parity:
                continue
            x,y = 5+row*.3, -1.08+column*.27
            offset = len(points)
            points.extend([(x,y,.004),(x+.3,y,.004),(x+.3,y+.27,.004),(x,y+.27,.004)])
            faces.append(tuple(range(offset,offset+4)))
    mesh(f'StartLine{parity}', points, faces, material)
lines.append('}')
(Path(__file__).resolve().parents[1] / 'demo/track.usda').write_text('\n'.join(lines)+'\n')
print(f'2 continuous wall meshes, {len(path)} road quads')
